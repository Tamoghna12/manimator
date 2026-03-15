"""Tests for manimator.analytics — YouTube analytics and insights."""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from manimator.analytics import Analytics


@pytest.fixture
def analytics():
    """Analytics instance with in-memory DB and pre-populated data."""
    a = Analytics(db_path=":memory:")

    # Create the videos table (pipeline normally does this)
    a._conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            topic TEXT,
            provider TEXT,
            model TEXT,
            domain TEXT,
            structure TEXT,
            format TEXT,
            theme TEXT,
            status TEXT NOT NULL DEFAULT 'done',
            storyboard_json TEXT,
            video_path TEXT,
            youtube_id TEXT,
            youtube_url TEXT,
            created_at TEXT,
            completed_at TEXT,
            error TEXT
        );
    """)

    # Insert test videos
    now = datetime.now(timezone.utc).isoformat()
    a._conn.execute(
        "INSERT INTO videos (id, topic, domain, youtube_id, youtube_url, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'done', ?)",
        ("v1", "CRISPR guide", "biology_reel", "yt_abc", "https://youtube.com/watch?v=yt_abc", now),
    )
    a._conn.execute(
        "INSERT INTO videos (id, topic, domain, youtube_id, youtube_url, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'done', ?)",
        ("v2", "Quantum basics", "physics_reel", "yt_def", "https://youtube.com/watch?v=yt_def", now),
    )
    a._conn.execute(
        "INSERT INTO videos (id, topic, domain, youtube_id, youtube_url, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'done', ?)",
        ("v3", "ML intro", "cs_reel", "yt_ghi", "https://youtube.com/watch?v=yt_ghi", now),
    )

    # Insert test metrics (3 days for v1, 2 for v2, 1 for v3)
    today = datetime.now(timezone.utc).date()
    synced = datetime.now(timezone.utc).isoformat()

    metrics_data = [
        # v1 — biology — 3 days, high views
        ("v1", str(today - timedelta(days=2)), 100, 10, 5, 2, 50.0, 30.0, 500, 0.20),
        ("v1", str(today - timedelta(days=1)), 150, 15, 8, 3, 75.0, 32.0, 600, 0.25),
        ("v1", str(today), 200, 20, 10, 5, 100.0, 35.0, 700, 0.28),
        # v2 — physics — 2 days, medium views
        ("v2", str(today - timedelta(days=1)), 80, 8, 3, 1, 40.0, 28.0, 400, 0.20),
        ("v2", str(today), 120, 12, 5, 2, 60.0, 30.0, 500, 0.24),
        # v3 — cs — 1 day, low views
        ("v3", str(today), 50, 5, 2, 1, 25.0, 25.0, 200, 0.25),
    ]

    for vid, date, views, likes, comments, shares, wt, avd, imp, ctr in metrics_data:
        a._conn.execute(
            "INSERT INTO metrics (id, video_id, date, views, likes, comments, shares, "
            "watch_time_minutes, avg_view_duration_seconds, impressions, ctr, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), vid, date, views, likes, comments, shares, wt, avd, imp, ctr, synced),
        )

    a._conn.commit()
    yield a
    a.close()


class TestGetVideoStats:
    def test_aggregates_across_days(self, analytics):
        stats = analytics.get_video_stats("v1")
        assert stats is not None
        assert stats["total_views"] == 450  # 100 + 150 + 200
        assert stats["total_likes"] == 45
        assert stats["days_tracked"] == 3

    def test_unknown_video_returns_none(self, analytics):
        assert analytics.get_video_stats("nonexistent") is None


class TestGetTopVideos:
    def test_sorted_by_views(self, analytics):
        top = analytics.get_top_videos(metric="views", limit=10)
        assert len(top) == 3
        assert top[0]["video_id"] == "v1"  # 450 views
        assert top[0]["total_views"] == 450

    def test_sorted_by_likes(self, analytics):
        top = analytics.get_top_videos(metric="likes", limit=10)
        assert top[0]["video_id"] == "v1"  # 45 likes
        assert top[0]["total_likes"] == 45

    def test_respects_limit(self, analytics):
        top = analytics.get_top_videos(metric="views", limit=1)
        assert len(top) == 1

    def test_invalid_metric_raises(self, analytics):
        with pytest.raises(ValueError, match="Invalid metric"):
            analytics.get_top_videos(metric="subscribers")


class TestGetDomainPerformance:
    def test_groups_by_domain(self, analytics):
        perf = analytics.get_domain_performance(days=30)
        assert "biology_reel" in perf
        assert "physics_reel" in perf
        assert "cs_reel" in perf
        assert perf["biology_reel"]["count"] == 1
        assert perf["biology_reel"]["total_views"] == 450

    def test_avg_views_calculated(self, analytics):
        perf = analytics.get_domain_performance(days=30)
        # biology has 1 video with 450 total views
        assert perf["biology_reel"]["avg_views"] == 450.0


class TestGetInsights:
    def test_has_all_keys(self, analytics):
        insights = analytics.get_insights()
        expected_keys = {
            "total_videos", "total_views", "avg_views_per_video",
            "best_domain", "worst_domain", "best_video",
            "best_posting_day", "avg_ctr", "data_freshness",
        }
        assert expected_keys.issubset(insights.keys())

    def test_best_domain_correct(self, analytics):
        insights = analytics.get_insights()
        # biology_reel has 450 views for 1 video → avg 450
        assert insights["best_domain"] == "biology_reel"

    def test_total_views_correct(self, analytics):
        insights = analytics.get_insights()
        # v1=450, v2=200, v3=50 = 700
        assert insights["total_views"] == 700

    def test_best_video(self, analytics):
        insights = analytics.get_insights()
        assert insights["best_video"]["video_id"] == "v1"
        assert insights["best_video"]["total_views"] == 450


class TestSyncMetrics:
    @patch("manimator.analytics.Analytics._build_analytics_service")
    def test_api_called_per_video(self, mock_build, analytics):
        """Sync calls the analytics API for each video with a youtube_id."""
        mock_svc = MagicMock()
        mock_build.return_value = mock_svc

        mock_query = MagicMock()
        mock_svc.reports.return_value.query.return_value = mock_query
        mock_query.execute.return_value = {"rows": []}

        count = analytics.sync_metrics(days=7)
        assert count == 0
        # Should have been called once per video with youtube_id (3 videos)
        assert mock_svc.reports.return_value.query.call_count == 3
