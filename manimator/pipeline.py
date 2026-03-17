"""
Batch pipeline — topic queue, storyboard generation, rendering, and optional upload.

Persists state in SQLite (WAL mode, serialised writes via threading.Lock).
Transient failures (network, rate limit, render timeout) are retried with
exponential backoff. Permanent failures (schema, auth, missing fields) are
dead-lettered immediately without retry. [web:148][web:154]

DB default:    ~/.local/share/manimator/pipeline.db
Renders to:    ~/.local/share/manimator/renders/
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

log = logging.getLogger(__name__)

DB_PATH    = Path.home() / ".local" / "share" / "manimator" / "pipeline.db"
RENDER_DIR = Path.home() / ".local" / "share" / "manimator" / "renders"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS topics (
    id          TEXT PRIMARY KEY,
    topic       TEXT NOT NULL,
    category    TEXT,
    domain      TEXT,
    structure   TEXT,
    format      TEXT,
    theme       TEXT,
    voice       TEXT,
    priority    INTEGER DEFAULT 0,
    used        INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id               TEXT PRIMARY KEY,
    topic            TEXT,
    category         TEXT,
    provider         TEXT,
    model            TEXT,
    domain           TEXT,
    structure        TEXT,
    format           TEXT,
    theme            TEXT,
    voice            TEXT,
    status           TEXT NOT NULL DEFAULT 'queued',
    storyboard_json  TEXT,
    video_path       TEXT,
    youtube_id       TEXT,
    youtube_url      TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    completed_at     TEXT,
    error            TEXT,
    error_type       TEXT,
    attempt_count    INTEGER DEFAULT 0,
    token_usage      TEXT
);
"""

# ── Valid vocabulary ───────────────────────────────────────────────────────

_VALID_FORMATS = frozenset({
    "instagram_reel", "tiktok", "youtube_short", "instagram_square",
    "presentation", "linkedin", "linkedin_square",
})
_VALID_THEMES     = frozenset({"wong", "npg", "tol_bright"})
_VALID_VOICES     = frozenset({"aria", "guy", "jenny", "davis", "andrew", "emma"})
_VALID_STRUCTURES = frozenset({"explainer", "short", "social_reel", "data_heavy", "tutorial"})

_PORTRAIT_FORMATS = frozenset({
    "instagram_reel", "tiktok", "youtube_short", "instagram_square",
})


# ── Error hierarchy ────────────────────────────────────────────────────────

class PipelineError(Exception):
    """Base class for pipeline errors."""


class TransientError(PipelineError):
    """
    Retry-eligible: network timeouts, rate limits, render crashes,
    transient server 5xx. [web:148][web:156]
    """


class PermanentError(PipelineError):
    """
    Dead-letter immediately: schema validation, auth failures,
    malformed payloads, missing required fields. [web:148]
    """


def _classify(exc: Exception) -> type[TransientError] | type[PermanentError]:
    """
    Classify an arbitrary exception as Transient or Permanent.
    Uses message heuristics; callers may override by raising the typed
    subclasses directly.
    """
    msg = str(exc).lower()
    # Permanent signals
    if any(t in msg for t in (
        "validationerror", "schema", "auth", "401", "403",
        "forbidden", "unauthorized", "missing field", "invalid format",
    )):
        return PermanentError
    # Transient signals [web:156]
    if any(t in msg for t in (
        "timeout", "rate limit", "429", "503", "connection",
        "temporarily unavailable", "network", "render failed",
    )):
        return TransientError
    # Default: transient (safe — will exhaust retries and dead-letter)
    return TransientError


# ── Result type ────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    video_id:  str
    topic:     str
    status:    str                         # "done" | "failed" | "dead_letter"
    error:     str | None   = None
    error_type: str | None  = None         # "transient" | "permanent"
    youtube_url: str | None = None
    video_path: str | None  = None
    token_usage: dict       = field(default_factory=dict)
    attempts:  int          = 0


# ── Helpers ────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "_", text)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _backoff(attempt: int, base: float = 2.0, cap: float = 30.0) -> float:
    """Full-jitter exponential backoff. [web:148][web:150]"""
    import random
    ceiling = min(cap, base ** attempt)
    return random.uniform(0, ceiling)


# ── CSV parser ─────────────────────────────────────────────────────────────

def parse_csv(csv_text: str) -> tuple[list[dict], list[dict]]:
    """
    Parse CSV into (topics, warnings).
    Required column: topic. All others are optional with sane defaults.
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if reader.fieldnames is None:
        return [], [{"row": 1, "error": "Empty or headerless CSV"}]

    topics:   list[dict] = []
    warnings: list[dict] = []

    _defaults = {
        "structure": ("social_reel",  _VALID_STRUCTURES),
        "format":    ("instagram_reel", _VALID_FORMATS),
        "theme":     ("wong",          _VALID_THEMES),
        "voice":     ("aria",          _VALID_VOICES),
    }

    for row_num, raw in enumerate(reader, start=2):
        row  = {k.strip().lower(): (v or "").strip() for k, v in raw.items()}
        topic = row.get("topic", "").strip()
        if not topic or topic.startswith("#"):
            continue

        entry: dict  = {"topic": topic}
        row_warns: list[str] = []

        for key, (default, valid_set) in _defaults.items():
            val = row.get(key) or default
            if val not in valid_set:
                row_warns.append(f"unknown {key} '{val}' — using {default}")
                val = default
            entry[key] = val

        entry["category"] = row.get("category") or None
        entry["domain"]   = row.get("domain")   or None

        try:
            entry["priority"] = int(row.get("priority") or "0")
        except ValueError:
            row_warns.append("priority must be an integer — using 0")
            entry["priority"] = 0

        topics.append(entry)
        if row_warns:
            warnings.append({"row": row_num, "topic": topic, "warnings": row_warns})

    return topics, warnings


# ── Pipeline ───────────────────────────────────────────────────────────────

class Pipeline:
    """
    Batch video production pipeline backed by SQLite.

    Write access is serialised with a threading.Lock so multiple threads
    can share one Pipeline instance safely. [web:144][web:149]
    WAL mode allows concurrent reads to proceed without blocking.

    Use as a context manager for guaranteed connection cleanup:
        with Pipeline() as pipe:
            pipe.run_pipeline(...)
    """

    STALE_MINUTES     = 15
    DAILY_UPLOAD_LIMIT = 6
    MAX_ATTEMPTS      = 3      # per video before permanent dead-letter

    def __init__(
        self,
        db_path: str | Path | None = None,
        render_dir: Path | None    = None,
        on_progress: Callable[[str, str, str], None] | None = None,
    ):
        """
        Args:
            db_path:     SQLite path or ":memory:" for tests.
            render_dir:  Output directory for rendered videos.
            on_progress: Optional callback(video_id, stage, message).
        """
        import sqlite3

        self._db_path    = str(db_path or DB_PATH)
        self._render_dir = render_dir or RENDER_DIR
        self._on_progress = on_progress
        self._lock       = threading.Lock()   # serialises all writes [web:144]

        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            timeout=30,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.executescript(_SCHEMA_SQL)
        self._migrate()

    # ── Context manager ────────────────────────────────────────────────

    def __enter__(self) -> "Pipeline":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Write serialisation ────────────────────────────────────────────

    @contextmanager
    def _write(self) -> Iterator[None]:
        """Context manager that acquires the write lock and commits on exit."""
        with self._lock:
            try:
                yield
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _progress(self, video_id: str, stage: str, msg: str) -> None:
        log.info("[%s] %s — %s", stage, video_id[:8], msg)
        if self._on_progress:
            self._on_progress(video_id, stage, msg)

    # ── Schema migration ───────────────────────────────────────────────

    def _migrate(self) -> None:
        """Add columns introduced after initial schema (idempotent)."""
        new_cols = [
            ("topics", "category TEXT"),
            ("topics", "voice TEXT"),
            ("videos", "category TEXT"),
            ("videos", "voice TEXT"),
            ("videos", "updated_at TEXT"),
            ("videos", "error_type TEXT"),
            ("videos", "attempt_count INTEGER DEFAULT 0"),
            ("videos", "token_usage TEXT"),
        ]
        with self._write():
            for table, col_def in new_cols:
                try:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
                except Exception:
                    pass   # column already exists

    # ── Topic management ───────────────────────────────────────────────

    def add_topics(self, topics: list[dict]) -> list[str]:
        """Bulk-insert topics. Returns list of generated UUIDs."""
        ids = []
        with self._write():
            for t in topics:
                tid = str(uuid.uuid4())
                self._conn.execute(
                    "INSERT INTO topics "
                    "(id, topic, category, domain, structure, format, theme, voice, "
                    "priority, used, created_at) VALUES (?,?,?,?,?,?,?,?,?,0,?)",
                    (
                        tid,
                        t["topic"],
                        t.get("category"),
                        t.get("domain"),
                        t.get("structure", "explainer"),
                        t.get("format", "instagram_reel"),
                        t.get("theme", "wong"),
                        t.get("voice"),
                        t.get("priority", 0),
                        _now(),
                    ),
                )
                ids.append(tid)
        return ids

    def list_topics(
        self, unused_only: bool = True, limit: int = 50,
    ) -> list[dict]:
        """Return topics ordered by priority DESC, created_at ASC."""
        sql  = "SELECT * FROM topics"
        args: list = [limit]
        if unused_only:
            sql += " WHERE used = 0"
        sql += " ORDER BY priority DESC, created_at ASC LIMIT ?"
        return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    # ── Storyboard import ──────────────────────────────────────────────

    def add_storyboards(self, storyboards: list[dict]) -> list[str]:
        """
        Import pre-written storyboards directly, bypassing the LLM.
        Creates video rows with status='queued' and storyboard_json set.
        """
        ids = []
        with self._write():
            for entry in storyboards:
                vid  = str(uuid.uuid4())
                sb   = entry["storyboard"]
                meta = sb.get("meta", {})
                fmt   = entry.get("format") or meta.get("format", "instagram_reel")
                theme = entry.get("theme")  or meta.get("color_theme", "wong")
                now   = _now()
                self._conn.execute(
                    "INSERT INTO videos (id, topic, provider, domain, format, theme, "
                    "status, storyboard_json, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,'queued',?,?,?)",
                    (
                        vid,
                        meta.get("title", "Untitled"),
                        "manual",
                        entry.get("domain"),
                        fmt, theme,
                        json.dumps(sb), now, now,
                    ),
                )
                ids.append(vid)
        return ids

    # ── Stale recovery ─────────────────────────────────────────────────

    def recover_stale(self) -> int:
        """
        Reset videos stuck in transient states to 'failed' using
        updated_at (not created_at) so long-running renders aren't
        prematurely killed. [web:149]
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=self.STALE_MINUTES)
        ).isoformat()
        with self._write():
            cur = self._conn.execute(
                "UPDATE videos SET status='failed', error_type='transient', "
                "error='Recovered: stale state exceeded timeout', updated_at=? "
                "WHERE status IN ('generating','rendering','uploading') "
                "AND updated_at < ?",
                (_now(), cutoff),
            )
        count = cur.rowcount
        if count:
            log.warning("Recovered %d stale videos", count)
        return count

    # ── Upload quota ───────────────────────────────────────────────────

    def _uploads_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM videos "
            "WHERE youtube_id IS NOT NULL AND completed_at >= ?",
            (today,),
        ).fetchone()
        return row["cnt"] if row else 0

    def _check_quota(self) -> None:
        used = self._uploads_today()
        if used >= self.DAILY_UPLOAD_LIMIT:
            raise PermanentError(
                f"YouTube daily upload quota reached ({used}/{self.DAILY_UPLOAD_LIMIT}). "
                "Retry tomorrow or request a quota increase in Google Cloud Console."
            )

    # ── Single-video helpers ───────────────────────────────────────────

    def _set_status(self, vid: str, status: str, **extra) -> None:
        """Update video status + updated_at atomically."""
        fields = {"status": status, "updated_at": _now(), **extra}
        setters = ", ".join(f"{k}=?" for k in fields)
        with self._write():
            self._conn.execute(
                f"UPDATE videos SET {setters} WHERE id=?",
                (*fields.values(), vid),
            )

    def _generate_one(
        self, vid: str, topic_row: dict,
        provider: str, model: str | None,
        api_key: str | None, base_url: str,
    ) -> dict:
        from manimator.llm import generate_storyboard

        self._set_status(vid, "generating")
        self._progress(vid, "generate", f"calling {provider}")

        result = generate_storyboard(
            topic=topic_row["topic"],
            provider=provider,
            model=model,
            api_key=api_key,
            domain=topic_row.get("domain"),
            structure=topic_row.get("structure", "explainer"),
            format_type=topic_row.get("format", "instagram_reel"),
            theme=topic_row.get("theme", "wong"),
            base_url=base_url,
        )

        # Persist storyboard + token usage
        with self._write():
            self._conn.execute(
                "UPDATE videos SET storyboard_json=?, token_usage=?, updated_at=? WHERE id=?",
                (
                    json.dumps(result.storyboard),
                    json.dumps(result.usage),
                    _now(), vid,
                ),
            )
        return result.storyboard

    def _render_one(
        self, vid: str, storyboard: dict,
        topic_row: dict, narrate: bool,
        voice: str, music: str,
    ) -> Path:
        self._set_status(vid, "rendering")
        self._progress(vid, "render", "starting")

        category  = topic_row.get("category") or ""
        out_dir   = (self._render_dir / _slugify(category)) if category else self._render_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path  = out_dir / f"{vid}.mp4"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir=str(self._render_dir),
        ) as f:
            json.dump(storyboard, f, indent=2)
            json_path = Path(f.name)

        fmt         = topic_row.get("format", "instagram_reel")
        is_portrait = fmt in _PORTRAIT_FORMATS
        module      = "manimator.portrait" if is_portrait else "manimator.orchestrator"

        cmd = ["python", "-m", module, "-s", str(json_path), "-o", str(out_path)]
        if is_portrait:
            cmd.extend(["--format", fmt])
        else:
            cmd.extend(["-q", "low"])
        if narrate:
            cmd.extend(["--narrate", "--voice", voice])
        if music and music not in ("", "none"):
            cmd.extend(["--music", music])

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            raise TransientError(f"Render timeout after 600s for video {vid}")
        finally:
            json_path.unlink(missing_ok=True)

        if r.returncode != 0 or not out_path.exists():
            stderr = (r.stderr or "")[-400:]
            raise TransientError(f"Render failed (exit {r.returncode}): {stderr}")

        self._set_status(vid, "rendering", video_path=str(out_path))
        self._progress(vid, "render", f"done → {out_path.name}")
        return out_path

    def _upload_one(
        self, vid: str, video_path: Path,
        storyboard: dict, privacy: str,
    ) -> tuple[str, str]:
        self._check_quota()
        self._set_status(vid, "uploading")
        self._progress(vid, "upload", "starting")

        from manimator.uploader import upload_short

        result = upload_short(
            video_path=str(video_path),
            storyboard_data=storyboard,
            privacy=privacy,
        )
        with self._write():
            self._conn.execute(
                "UPDATE videos SET youtube_id=?, youtube_url=?, updated_at=? WHERE id=?",
                (result["video_id"], result["url"], _now(), vid),
            )
        self._progress(vid, "upload", result["url"])
        return result["video_id"], result["url"]

    # ── Per-video orchestration with classified retry ──────────────────

    def _run_one(
        self,
        vid:        str,
        topic_row:  dict,
        provider:   str  | None,
        model:      str  | None,
        api_key:    str  | None,
        base_url:   str,
        upload:     bool,
        privacy:    str,
        narrate:    bool,
        voice:      str,
        music:      str,
        has_storyboard: bool = False,
    ) -> PipelineResult:
        """
        Run generate → render → upload for a single video with per-stage
        transient/permanent error classification. [web:148][web:154]
        Permanent errors dead-letter immediately; transient errors retry
        up to MAX_ATTEMPTS with exponential backoff.
        """
        res = PipelineResult(
            video_id=vid,
            topic=topic_row.get("topic", ""),
            status="failed",
        )

        for attempt in range(self.MAX_ATTEMPTS):
            res.attempts = attempt + 1
            try:
                # ── Generate ────────────────────────────────────────
                if not has_storyboard:
                    storyboard = self._generate_one(
                        vid, topic_row, provider, model, api_key, base_url,
                    )
                    has_storyboard = True
                else:
                    row = self._conn.execute(
                        "SELECT storyboard_json FROM videos WHERE id=?", (vid,)
                    ).fetchone()
                    storyboard = json.loads(row["storyboard_json"])

                # ── Render ──────────────────────────────────────────
                eff_voice = topic_row.get("voice") or voice
                video_path = self._render_one(
                    vid, storyboard, topic_row, narrate, eff_voice, music,
                )
                res.video_path = str(video_path)

                # ── Upload ──────────────────────────────────────────
                if upload:
                    _, url = self._upload_one(vid, video_path, storyboard, privacy)
                    res.youtube_url = url

                # ── Done ─────────────────────────────────────────────
                with self._write():
                    self._conn.execute(
                        "UPDATE videos SET status='done', completed_at=?, "
                        "attempt_count=?, updated_at=? WHERE id=?",
                        (_now(), res.attempts, _now(), vid),
                    )
                res.status = "done"
                self._progress(vid, "pipeline", "done")
                return res

            except PermanentError as exc:
                # Dead-letter immediately — retrying won't help [web:148]
                log.error("[permanent] %s: %s", vid[:8], exc)
                with self._write():
                    self._conn.execute(
                        "UPDATE videos SET status='dead_letter', error=?, "
                        "error_type='permanent', attempt_count=?, "
                        "completed_at=?, updated_at=? WHERE id=?",
                        (str(exc)[:500], res.attempts, _now(), _now(), vid),
                    )
                res.status     = "dead_letter"
                res.error      = str(exc)
                res.error_type = "permanent"
                return res

            except Exception as exc:
                err_cls = _classify(exc)
                if err_cls is PermanentError:
                    # Reclassified as permanent
                    log.error("[permanent-reclassified] %s: %s", vid[:8], exc)
                    with self._write():
                        self._conn.execute(
                            "UPDATE videos SET status='dead_letter', error=?, "
                            "error_type='permanent', attempt_count=?, "
                            "completed_at=?, updated_at=? WHERE id=?",
                            (str(exc)[:500], res.attempts, _now(), _now(), vid),
                        )
                    res.status     = "dead_letter"
                    res.error      = str(exc)
                    res.error_type = "permanent"
                    return res

                # Transient — log and backoff before retry [web:148][web:150]
                res.error      = str(exc)
                res.error_type = "transient"
                log.warning(
                    "[transient attempt %d/%d] %s: %s",
                    attempt + 1, self.MAX_ATTEMPTS, vid[:8], exc,
                )
                with self._write():
                    self._conn.execute(
                        "UPDATE videos SET status='failed', error=?, "
                        "error_type='transient', attempt_count=?, updated_at=? WHERE id=?",
                        (str(exc)[:500], res.attempts, _now(), vid),
                    )

                if attempt < self.MAX_ATTEMPTS - 1:
                    delay = _backoff(attempt + 1)
                    log.info("Backing off %.1fs before retry", delay)
                    time.sleep(delay)

        # Exhausted all attempts
        with self._write():
            self._conn.execute(
                "UPDATE videos SET status='dead_letter', error_type='transient', "
                "completed_at=?, updated_at=? WHERE id=?",
                (_now(), _now(), vid),
            )
        res.status = "dead_letter"
        return res

    # ── Public pipeline entry points ───────────────────────────────────

    def run_pipeline(
        self,
        provider:   str,
        model:      str | None = None,
        api_key:    str | None = None,
        base_url:   str        = "",
        limit:      int        = 5,
        upload:     bool       = False,
        privacy:    str        = "private",
        narrate:    bool       = False,
        voice:      str        = "aria",
        music:      str        = "",
    ) -> list[PipelineResult]:
        """Process up to *limit* unused topics: generate → render → upload."""
        self.recover_stale()
        topics  = self.list_topics(unused_only=True, limit=limit)
        results = []

        for topic_row in topics:
            vid = str(uuid.uuid4())
            with self._write():
                self._conn.execute(
                    "UPDATE topics SET used=1 WHERE id=?", (topic_row["id"],)
                )
                now = _now()
                self._conn.execute(
                    "INSERT INTO videos "
                    "(id, topic, category, provider, model, domain, structure, "
                    "format, theme, voice, status, attempt_count, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,'queued',0,?,?)",
                    (
                        vid,
                        topic_row["topic"],
                        topic_row.get("category"),
                        provider, model,
                        topic_row.get("domain"),
                        topic_row.get("structure", "explainer"),
                        topic_row.get("format", "instagram_reel"),
                        topic_row.get("theme", "wong"),
                        topic_row.get("voice"),
                        now, now,
                    ),
                )

            res = self._run_one(
                vid, topic_row, provider, model, api_key, base_url,
                upload, privacy, narrate, voice, music,
            )
            results.append(res)

        return results

    def run_renders(
        self,
        limit:   int  = 5,
        upload:  bool = False,
        privacy: str  = "private",
        narrate: bool = False,
        voice:   str  = "aria",
        music:   str  = "",
    ) -> list[PipelineResult]:
        """Render videos that already have storyboard_json (no LLM needed)."""
        self.recover_stale()
        rows = self._conn.execute(
            "SELECT * FROM videos WHERE status='queued' AND storyboard_json IS NOT NULL "
            "ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()

        results = []
        for row in rows:
            vid       = row["id"]
            topic_row = dict(row)
            res = self._run_one(
                vid, topic_row, None, None, None, "",
                upload, privacy, narrate, voice, music,
                has_storyboard=True,
            )
            results.append(res)
        return results

    # ── Status / query helpers ─────────────────────────────────────────

    def get_status(self) -> dict:
        rows   = self._conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM videos GROUP BY status"
        ).fetchall()
        counts = {r["status"]: r["cnt"] for r in rows}
        for s in ("queued", "generating", "rendering", "uploading",
                  "done", "failed", "dead_letter"):
            counts.setdefault(s, 0)
        counts["total"] = sum(v for k, v in counts.items() if k != "total")
        return counts

    def list_videos(
        self, status: str | None = None, limit: int = 20,
    ) -> list[dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM videos WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_video(self, video_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM videos WHERE id=?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

    def retry_failed(self, limit: int = 5) -> int:
        """
        Reset transient-failed (not dead_letter) videos back to queued.
        Dead-lettered permanent failures are intentionally excluded. [web:148]
        """
        rows = self._conn.execute(
            "SELECT id FROM videos WHERE status='failed' AND "
            "(error_type='transient' OR error_type IS NULL) LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return 0
        ids          = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        with self._write():
            self._conn.execute(
                f"UPDATE videos SET status='queued', error=NULL, "
                f"error_type=NULL, updated_at=? WHERE id IN ({placeholders})",
                (_now(), *ids),
            )
        return len(ids)

    def requeue_dead_letters(self, limit: int = 5) -> int:
        """
        Manually requeue dead-lettered videos (e.g. after a code fix).
        Resets attempt_count so they get fresh retries.
        """
        rows = self._conn.execute(
            "SELECT id FROM videos WHERE status='dead_letter' LIMIT ?", (limit,)
        ).fetchall()
        if not rows:
            return 0
        ids          = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        with self._write():
            self._conn.execute(
                f"UPDATE videos SET status='queued', error=NULL, error_type=NULL, "
                f"attempt_count=0, updated_at=? WHERE id IN ({placeholders})",
                (_now(), *ids),
            )
        return len(ids)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

