"""
YouTube Analytics — sync metrics and generate performance insights.

Extends the pipeline SQLite database with a metrics table for per-video
daily analytics. Data is pulled from the YouTube Analytics API v2.

Note: YouTube Analytics data typically lags 48-72 hours behind real-time.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path.home() / ".local" / "share" / "manimator" / "pipeline.db"

_METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    date TEXT NOT NULL,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    watch_time_minutes REAL DEFAULT 0.0,
    avg_view_duration_seconds REAL DEFAULT 0.0,
    impressions INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0.0,
    synced_at TEXT NOT NULL,
    UNIQUE(video_id, date)
);
"""


class Analytics:
    """YouTube analytics syncing and insight generation."""

    def __init__(self, db_path=None):
        import sqlite3
        import uuid

        self._uuid = uuid
        self._db_path = db_path or str(DB_PATH)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_metrics_table()

    def _init_metrics_table(self):
        """Create metrics table if it doesn't exist."""
        self._conn.executescript(_METRICS_SCHEMA)

    def _build_analytics_service(self):
        """Build authenticated YouTube Analytics API v2 service."""
        from googleapiclient.discovery import build
        from manimator.uploader import _get_credentials

        creds = _get_credentials()
        return build("youtubeAnalytics", "v2", credentials=creds)

    def sync_metrics(self, days: int = 7) -> int:
        """Pull per-video daily metrics from YouTube Analytics API.

        Args:
            days: Number of days of history to sync.

        Returns:
            Number of metric rows inserted/updated.
        """
        import uuid

        # Get all videos with a youtube_id
        videos = self._conn.execute(
            "SELECT id, youtube_id FROM videos WHERE youtube_id IS NOT NULL"
        ).fetchall()

        if not videos:
            log.info("No uploaded videos to sync metrics for.")
            return 0

        analytics = self._build_analytics_service()
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)
        now = datetime.now(timezone.utc).isoformat()
        count = 0

        for video in videos:
            try:
                response = analytics.reports().query(
                    ids="channel==MINE",
                    startDate=str(start_date),
                    endDate=str(end_date),
                    metrics="views,likes,comments,shares,estimatedMinutesWatched,"
                            "averageViewDuration,impressions,impressionClickThroughRate",
                    dimensions="day",
                    filters=f"video=={video['youtube_id']}",
                    sort="day",
                ).execute()

                for row in response.get("rows", []):
                    day = row[0]
                    self._conn.execute(
                        "INSERT OR REPLACE INTO metrics "
                        "(id, video_id, date, views, likes, comments, shares, "
                        "watch_time_minutes, avg_view_duration_seconds, impressions, ctr, synced_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(uuid.uuid4()),
                            video["id"],
                            day,
                            row[1],  # views
                            row[2],  # likes
                            row[3],  # comments
                            row[4],  # shares
                            row[5],  # watch_time_minutes
                            row[6],  # avg_view_duration
                            row[7],  # impressions
                            row[8],  # ctr
                            now,
                        ),
                    )
                    count += 1

            except Exception as e:
                log.error("Failed to sync metrics for video %s: %s", video["youtube_id"], e)

        self._conn.commit()
        log.info("Synced %d metric rows across %d videos", count, len(videos))
        return count

    def get_video_stats(self, video_id: str) -> dict | None:
        """Get aggregated stats for a single video.

        Returns:
            dict with total_views, total_likes, total_comments, avg_duration,
            days_tracked — or None if no data.
        """
        row = self._conn.execute(
            "SELECT "
            "  SUM(views) as total_views, "
            "  SUM(likes) as total_likes, "
            "  SUM(comments) as total_comments, "
            "  SUM(shares) as total_shares, "
            "  SUM(watch_time_minutes) as total_watch_time, "
            "  AVG(avg_view_duration_seconds) as avg_duration, "
            "  COUNT(*) as days_tracked "
            "FROM metrics WHERE video_id = ?",
            (video_id,),
        ).fetchone()

        if not row or row["days_tracked"] == 0:
            return None

        return {
            "video_id": video_id,
            "total_views": row["total_views"] or 0,
            "total_likes": row["total_likes"] or 0,
            "total_comments": row["total_comments"] or 0,
            "total_shares": row["total_shares"] or 0,
            "total_watch_time": row["total_watch_time"] or 0.0,
            "avg_duration": row["avg_duration"] or 0.0,
            "days_tracked": row["days_tracked"],
        }

    def get_top_videos(
        self, metric: str = "views", limit: int = 10, days: int = 30
    ) -> list[dict]:
        """Get top-performing videos sorted by a metric.

        Args:
            metric: One of views, likes, comments, shares.
            limit: Max results to return.
            days: Only consider metrics from the last N days.
        """
        valid_metrics = {"views", "likes", "comments", "shares"}
        if metric not in valid_metrics:
            raise ValueError(f"Invalid metric: {metric}. Must be one of {valid_metrics}")

        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

        rows = self._conn.execute(
            f"SELECT video_id, SUM({metric}) as total "
            "FROM metrics WHERE date >= ? "
            "GROUP BY video_id ORDER BY total DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()

        results = []
        for r in rows:
            video = self._conn.execute(
                "SELECT topic, youtube_id, youtube_url, domain FROM videos WHERE id = ?",
                (r["video_id"],),
            ).fetchone()
            results.append({
                "video_id": r["video_id"],
                f"total_{metric}": r["total"],
                "topic": video["topic"] if video else None,
                "youtube_id": video["youtube_id"] if video else None,
                "youtube_url": video["youtube_url"] if video else None,
                "domain": video["domain"] if video else None,
            })

        return results

    def get_domain_performance(self, days: int = 30) -> dict:
        """Get aggregated performance grouped by domain.

        Returns:
            {domain: {count, total_views, avg_views, avg_ctr}}
        """
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

        rows = self._conn.execute(
            "SELECT v.domain, "
            "  COUNT(DISTINCT v.id) as count, "
            "  SUM(m.views) as total_views, "
            "  AVG(m.ctr) as avg_ctr "
            "FROM videos v "
            "JOIN metrics m ON v.id = m.video_id "
            "WHERE m.date >= ? AND v.domain IS NOT NULL "
            "GROUP BY v.domain",
            (cutoff,),
        ).fetchall()

        result = {}
        for r in rows:
            total_views = r["total_views"] or 0
            count = r["count"] or 1
            result[r["domain"]] = {
                "count": count,
                "total_views": total_views,
                "avg_views": total_views / count if count else 0,
                "avg_ctr": r["avg_ctr"] or 0.0,
            }

        return result

    def get_insights(self) -> dict:
        """Generate summary insights across all tracked videos.

        Returns dict with: total_videos, total_views, avg_views_per_video,
        best_domain, worst_domain, best_video, best_posting_day, avg_ctr,
        data_freshness.
        """
        # Total uploaded videos
        total_videos = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM videos WHERE youtube_id IS NOT NULL"
        ).fetchone()["cnt"]

        # Aggregate metrics
        agg = self._conn.execute(
            "SELECT SUM(views) as total_views, AVG(ctr) as avg_ctr FROM metrics"
        ).fetchone()
        total_views = agg["total_views"] or 0
        avg_ctr = agg["avg_ctr"] or 0.0

        # Best video by total views
        best_video_row = self._conn.execute(
            "SELECT video_id, SUM(views) as total "
            "FROM metrics GROUP BY video_id ORDER BY total DESC LIMIT 1"
        ).fetchone()
        best_video = None
        if best_video_row:
            v = self._conn.execute(
                "SELECT topic, youtube_url FROM videos WHERE id = ?",
                (best_video_row["video_id"],),
            ).fetchone()
            best_video = {
                "video_id": best_video_row["video_id"],
                "total_views": best_video_row["total"],
                "topic": v["topic"] if v else None,
                "youtube_url": v["youtube_url"] if v else None,
            }

        # Domain performance
        domain_perf = self.get_domain_performance(days=365)
        best_domain = max(domain_perf, key=lambda d: domain_perf[d]["avg_views"]) if domain_perf else None
        worst_domain = min(domain_perf, key=lambda d: domain_perf[d]["avg_views"]) if domain_perf else None

        # Best posting day — uses only the earliest metric date per video
        # (proxy for upload day) to avoid conflating accumulation days with
        # posting day. This is still correlational, not causal; see Kohavi et al.
        # (2020) Trustworthy Online Controlled Experiments, Cambridge UP.
        day_rows = self._conn.execute(
            "SELECT "
            "  CASE CAST(strftime('%w', first_date) AS INTEGER) "
            "    WHEN 0 THEN 'Sunday' WHEN 1 THEN 'Monday' WHEN 2 THEN 'Tuesday' "
            "    WHEN 3 THEN 'Wednesday' WHEN 4 THEN 'Thursday' "
            "    WHEN 5 THEN 'Friday' WHEN 6 THEN 'Saturday' END as day_name, "
            "  AVG(first_day_views) as avg_views "
            "FROM ("
            "  SELECT video_id, MIN(date) as first_date, views as first_day_views "
            "  FROM metrics GROUP BY video_id"
            ") sub "
            "GROUP BY strftime('%w', first_date) ORDER BY avg_views DESC LIMIT 1"
        ).fetchone()
        best_posting_day = day_rows["day_name"] if day_rows else None

        # Data freshness
        latest = self._conn.execute(
            "SELECT MAX(synced_at) as latest FROM metrics"
        ).fetchone()
        data_freshness = latest["latest"] if latest else None

        return {
            "total_videos": total_videos,
            "total_views": total_views,
            "avg_views_per_video": total_views / total_videos if total_videos else 0,
            "best_domain": best_domain,
            "worst_domain": worst_domain,
            "best_video": best_video,
            "best_posting_day": best_posting_day,
            "avg_ctr": avg_ctr,
            "data_freshness": data_freshness,
        }

    def close(self):
        """Close the database connection."""
        self._conn.close()
