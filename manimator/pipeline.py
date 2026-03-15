"""
Batch pipeline — topic queue, storyboard generation, rendering, and optional upload.

Persists state in SQLite so runs can be resumed and monitored.
DB default location: ~/.local/share/manimator/pipeline.db
Renders to: ~/.local/share/manimator/renders/
"""

import json
import logging
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path.home() / ".local" / "share" / "manimator" / "pipeline.db"
RENDER_DIR = Path.home() / ".local" / "share" / "manimator" / "renders"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    domain TEXT,
    structure TEXT,
    format TEXT,
    theme TEXT,
    priority INTEGER DEFAULT 0,
    used INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    topic TEXT,
    provider TEXT,
    model TEXT,
    domain TEXT,
    structure TEXT,
    format TEXT,
    theme TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    storyboard_json TEXT,
    video_path TEXT,
    youtube_id TEXT,
    youtube_url TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT
);
"""


class Pipeline:
    """Batch video production pipeline backed by SQLite."""

    def __init__(self, db_path=None):
        import sqlite3

        self._db_path = db_path or str(DB_PATH)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA_SQL)

    # ── Topic management ─────────────────────────────────────────────────

    def add_topics(self, topics: list[dict]) -> list[str]:
        """Bulk-insert topics. Each dict may have: topic, domain, structure,
        format, theme, priority. Returns list of generated UUIDs."""
        ids = []
        now = datetime.now(timezone.utc).isoformat()
        for t in topics:
            tid = str(uuid.uuid4())
            self._conn.execute(
                "INSERT INTO topics (id, topic, domain, structure, format, theme, priority, used, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (
                    tid,
                    t["topic"],
                    t.get("domain"),
                    t.get("structure", "explainer"),
                    t.get("format", "instagram_reel"),
                    t.get("theme", "wong"),
                    t.get("priority", 0),
                    now,
                ),
            )
            ids.append(tid)
        self._conn.commit()
        return ids

    def list_topics(self, unused_only: bool = True, limit: int = 50) -> list[dict]:
        """Return topics ordered by priority desc, created_at asc."""
        sql = "SELECT * FROM topics"
        if unused_only:
            sql += " WHERE used = 0"
        sql += " ORDER BY priority DESC, created_at ASC LIMIT ?"
        rows = self._conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── Pipeline execution ───────────────────────────────────────────────

    # ── Stale-state recovery ────────────────────────────────────────────

    STALE_MINUTES = 15

    def recover_stale(self) -> int:
        """Reset videos stuck in transient states (generating/rendering/uploading)
        for longer than STALE_MINUTES back to 'failed' so retry_failed can pick them up.

        Returns number of rows recovered.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=self.STALE_MINUTES)
        ).isoformat()
        cur = self._conn.execute(
            "UPDATE videos SET status = 'failed', "
            "error = 'Recovered: stale state exceeded timeout' "
            "WHERE status IN ('generating', 'rendering', 'uploading') "
            "AND created_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        count = cur.rowcount
        if count:
            log.warning("Recovered %d stale videos", count)
        return count

    # ── Upload quota tracking ────────────────────────────────────────────

    DAILY_UPLOAD_LIMIT = 6  # YouTube default: ~1,600 units/upload, 10,000/day

    def _uploads_today(self) -> int:
        """Count uploads completed today (UTC)."""
        today = datetime.now(timezone.utc).date().isoformat()
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM videos "
            "WHERE youtube_id IS NOT NULL AND completed_at >= ?",
            (today,),
        ).fetchone()
        return row["cnt"] if row else 0

    def _check_quota(self) -> None:
        """Raise RuntimeError if daily upload quota would be exceeded."""
        used = self._uploads_today()
        if used >= self.DAILY_UPLOAD_LIMIT:
            raise RuntimeError(
                f"YouTube daily upload quota reached ({used}/{self.DAILY_UPLOAD_LIMIT}). "
                "Try again tomorrow or request a quota increase from Google Cloud Console."
            )

    # ── Pipeline execution ───────────────────────────────────────────────

    def run_pipeline(
        self,
        provider: str,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "",
        limit: int = 5,
        upload: bool = False,
        privacy: str = "private",
        narrate: bool = False,
        voice: str = "aria",
        music: str = "",
    ) -> list[dict]:
        """Process up to *limit* unused topics through generate → render → upload."""
        # Recover any videos stuck in transient states from prior crashed runs
        self.recover_stale()

        topics = self.list_topics(unused_only=True, limit=limit)
        results = []

        for topic_row in topics:
            vid = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            # Mark topic used
            self._conn.execute("UPDATE topics SET used = 1 WHERE id = ?", (topic_row["id"],))
            self._conn.commit()

            # Create video row
            self._conn.execute(
                "INSERT INTO videos (id, topic, provider, model, domain, structure, format, theme, "
                "status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'generating', ?)",
                (
                    vid,
                    topic_row["topic"],
                    provider,
                    model,
                    topic_row["domain"],
                    topic_row["structure"],
                    topic_row["format"],
                    topic_row["theme"],
                    now,
                ),
            )
            self._conn.commit()

            try:
                storyboard = self._generate_one(
                    vid, topic_row, provider, model, api_key, base_url
                )
                video_path = self._render_one(
                    vid, storyboard, topic_row, narrate, voice, music
                )
                youtube_id = youtube_url = None
                if upload:
                    youtube_id, youtube_url = self._upload_one(
                        vid, video_path, storyboard, privacy
                    )

                self._conn.execute(
                    "UPDATE videos SET status = 'done', completed_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), vid),
                )
                self._conn.commit()
                results.append({"video_id": vid, "status": "done", "topic": topic_row["topic"]})

            except Exception as e:
                log.error("Pipeline failed for video %s: %s", vid, e)
                self._conn.execute(
                    "UPDATE videos SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
                    (str(e)[:500], datetime.now(timezone.utc).isoformat(), vid),
                )
                self._conn.commit()
                results.append({
                    "video_id": vid, "status": "failed",
                    "topic": topic_row["topic"], "error": str(e)[:500],
                })

        return results

    def _generate_one(self, vid, topic_row, provider, model, api_key, base_url):
        """Generate storyboard via LLM and persist JSON."""
        from manimator.llm import generate_storyboard

        storyboard = generate_storyboard(
            topic=topic_row["topic"],
            provider=provider,
            model=model,
            api_key=api_key,
            domain=topic_row["domain"],
            structure=topic_row.get("structure", "explainer"),
            format_type=topic_row.get("format", "instagram_reel"),
            theme=topic_row.get("theme", "wong"),
            base_url=base_url,
        )

        self._conn.execute(
            "UPDATE videos SET storyboard_json = ? WHERE id = ?",
            (json.dumps(storyboard), vid),
        )
        self._conn.commit()
        return storyboard

    def _render_one(self, vid, storyboard, topic_row, narrate, voice, music):
        """Render storyboard to video file via subprocess."""
        self._conn.execute("UPDATE videos SET status = 'rendering' WHERE id = ?", (vid,))
        self._conn.commit()

        RENDER_DIR.mkdir(parents=True, exist_ok=True)
        output_path = RENDER_DIR / f"{vid}.webm"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir=str(RENDER_DIR)
        ) as f:
            json.dump(storyboard, f, indent=2)
            json_path = f.name

        fmt = topic_row.get("format", "instagram_reel")
        is_portrait = fmt in ("instagram_reel", "tiktok", "youtube_short", "instagram_square")
        module = "manimator.portrait" if is_portrait else "manimator.orchestrator"

        cmd = ["python", "-m", module, "-s", json_path, "-o", str(output_path)]
        if is_portrait:
            cmd.extend(["--format", fmt])
        else:
            cmd.extend(["-q", "low"])
        if narrate:
            cmd.extend(["--narrate", "--voice", voice])
        if music and music not in ("", "none"):
            cmd.extend(["--music", music])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        # Clean up temp JSON
        Path(json_path).unlink(missing_ok=True)

        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError(
                f"Render failed (exit {result.returncode}): "
                + (result.stderr[-300:] if result.stderr else "no output")
            )

        self._conn.execute(
            "UPDATE videos SET video_path = ? WHERE id = ?", (str(output_path), vid)
        )
        self._conn.commit()
        return output_path

    def _upload_one(self, vid, video_path, storyboard, privacy):
        """Upload rendered video to YouTube."""
        self._check_quota()

        self._conn.execute("UPDATE videos SET status = 'uploading' WHERE id = ?", (vid,))
        self._conn.commit()

        from manimator.uploader import upload_short

        result = upload_short(
            video_path=str(video_path),
            storyboard_data=storyboard,
            privacy=privacy,
        )

        self._conn.execute(
            "UPDATE videos SET youtube_id = ?, youtube_url = ? WHERE id = ?",
            (result["video_id"], result["url"], vid),
        )
        self._conn.commit()
        return result["video_id"], result["url"]

    # ── Status / queries ─────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return counts by status plus total."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM videos GROUP BY status"
        ).fetchall()
        counts = {r["status"]: r["cnt"] for r in rows}
        total = sum(counts.values())
        for s in ("queued", "generating", "rendering", "uploading", "done", "failed"):
            counts.setdefault(s, 0)
        counts["total"] = total
        return counts

    def list_videos(self, status: str | None = None, limit: int = 20) -> list[dict]:
        """List videos, optionally filtered by status."""
        if status:
            rows = self._conn.execute(
                "SELECT * FROM videos WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_video(self, video_id: str) -> dict | None:
        """Get a single video by ID."""
        row = self._conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

    def retry_failed(self, limit: int = 5) -> int:
        """Reset failed videos back to queued status. Returns count reset."""
        # SELECT IDs first since LIMIT in UPDATE requires special SQLite compilation
        rows = self._conn.execute(
            "SELECT id FROM videos WHERE status = 'failed' LIMIT ?", (limit,)
        ).fetchall()
        if not rows:
            return 0
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"UPDATE videos SET status = 'queued', error = NULL WHERE id IN ({placeholders})",
            ids,
        )
        self._conn.commit()
        return len(ids)

    def close(self):
        """Close the database connection."""
        self._conn.close()
