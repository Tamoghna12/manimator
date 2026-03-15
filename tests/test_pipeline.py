"""Tests for manimator.pipeline — batch pipeline with SQLite persistence."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from manimator.pipeline import Pipeline


@pytest.fixture
def pipe():
    """Pipeline backed by in-memory SQLite."""
    p = Pipeline(db_path=":memory:")
    yield p
    p.close()


@pytest.fixture
def sample_topics():
    return [
        {"topic": "How CRISPR works", "domain": "biology_reel", "structure": "social_reel",
         "format": "instagram_reel", "theme": "wong", "priority": 2},
        {"topic": "Quantum entanglement", "domain": "physics_reel", "structure": "social_reel",
         "format": "youtube_short", "theme": "wong", "priority": 1},
        {"topic": "Neural networks", "domain": "cs_reel", "structure": "social_reel",
         "format": "tiktok", "theme": "wong"},
    ]


class TestTopicManagement:
    def test_add_returns_uuids(self, pipe, sample_topics):
        ids = pipe.add_topics(sample_topics)
        assert len(ids) == 3
        assert all(isinstance(i, str) and len(i) == 36 for i in ids)

    def test_metadata_preserved(self, pipe, sample_topics):
        pipe.add_topics(sample_topics)
        topics = pipe.list_topics(unused_only=False)
        assert topics[0]["topic"] == "How CRISPR works"
        assert topics[0]["domain"] == "biology_reel"
        assert topics[0]["priority"] == 2

    def test_unused_filter(self, pipe, sample_topics):
        pipe.add_topics(sample_topics)
        assert len(pipe.list_topics(unused_only=True)) == 3
        # Mark one used
        pipe._conn.execute("UPDATE topics SET used = 1 WHERE topic = 'How CRISPR works'")
        pipe._conn.commit()
        unused = pipe.list_topics(unused_only=True)
        assert len(unused) == 2
        assert all(t["topic"] != "How CRISPR works" for t in unused)

    def test_priority_ordering(self, pipe, sample_topics):
        pipe.add_topics(sample_topics)
        topics = pipe.list_topics()
        # Higher priority first
        assert topics[0]["priority"] >= topics[1]["priority"]

    def test_limit(self, pipe, sample_topics):
        pipe.add_topics(sample_topics)
        assert len(pipe.list_topics(limit=1)) == 1


class TestPipelineStatus:
    def test_empty_status(self, pipe):
        status = pipe.get_status()
        assert status["total"] == 0
        assert status["done"] == 0
        assert status["failed"] == 0
        assert status["queued"] == 0

    def test_reflects_video_counts(self, pipe):
        now = "2026-01-01T00:00:00"
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, ?, ?)",
            ("v1", "test1", "done", now),
        )
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, ?, ?)",
            ("v2", "test2", "failed", now),
        )
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, ?, ?)",
            ("v3", "test3", "done", now),
        )
        pipe._conn.commit()
        status = pipe.get_status()
        assert status["done"] == 2
        assert status["failed"] == 1
        assert status["total"] == 3


class TestListVideos:
    def test_empty_list(self, pipe):
        assert pipe.list_videos() == []

    def test_status_filter(self, pipe):
        now = "2026-01-01T00:00:00"
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, ?, ?)",
            ("v1", "t1", "done", now),
        )
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, ?, ?)",
            ("v2", "t2", "failed", now),
        )
        pipe._conn.commit()
        done = pipe.list_videos(status="done")
        assert len(done) == 1
        assert done[0]["id"] == "v1"

    def test_get_video(self, pipe):
        now = "2026-01-01T00:00:00"
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, ?, ?)",
            ("v1", "t1", "done", now),
        )
        pipe._conn.commit()
        v = pipe.get_video("v1")
        assert v["topic"] == "t1"
        assert pipe.get_video("nonexistent") is None


class TestRunPipeline:
    @patch("manimator.pipeline.subprocess.run")
    @patch("manimator.pipeline.Pipeline._generate_one")
    def test_full_pipeline_no_upload(self, mock_gen, mock_run, pipe, sample_topics):
        """Pipeline generates and renders without uploading."""
        pipe.add_topics(sample_topics[:1])

        mock_gen.return_value = {
            "meta": {"title": "CRISPR", "format": "instagram_reel"},
            "scenes": [],
        }
        # _generate_one is mocked, so _render_one will be called.
        # We also mock _render_one to avoid subprocess:
        with patch.object(pipe, "_render_one", return_value="/tmp/test.webm"):
            results = pipe.run_pipeline(provider="openai", model="gpt-4o", limit=1, upload=False)

        assert len(results) == 1
        assert results[0]["status"] == "done"
        # Topic should be marked used
        unused = pipe.list_topics(unused_only=True)
        assert len(unused) == 0

    @patch("manimator.pipeline.Pipeline._render_one")
    @patch("manimator.pipeline.Pipeline._generate_one")
    def test_generation_failure_recorded(self, mock_gen, mock_render, pipe, sample_topics):
        """A failing generation records error and continues to next topic."""
        pipe.add_topics(sample_topics[:2])

        mock_gen.side_effect = [
            RuntimeError("LLM API down"),
            {"meta": {"title": "QE"}, "scenes": []},
        ]
        mock_render.return_value = "/tmp/test.webm"

        results = pipe.run_pipeline(provider="openai", limit=2)

        assert results[0]["status"] == "failed"
        assert "LLM API down" in results[0]["error"]
        assert results[1]["status"] == "done"

    @patch("manimator.pipeline.Pipeline._render_one")
    @patch("manimator.pipeline.Pipeline._generate_one")
    def test_limit_respected(self, mock_gen, mock_render, pipe, sample_topics):
        pipe.add_topics(sample_topics)
        mock_gen.return_value = {"meta": {"title": "T"}, "scenes": []}
        mock_render.return_value = "/tmp/test.webm"

        results = pipe.run_pipeline(provider="openai", limit=1)
        assert len(results) == 1


class TestRenderFailure:
    @patch("manimator.pipeline.Pipeline._generate_one")
    @patch("manimator.pipeline.Pipeline._render_one")
    def test_render_failure_records_error(self, mock_render, mock_gen, pipe, sample_topics):
        """Subprocess render failure is recorded and batch continues."""
        pipe.add_topics(sample_topics[:2])
        mock_gen.return_value = {"meta": {"title": "T"}, "scenes": []}
        mock_render.side_effect = [
            RuntimeError("Render failed (exit 1): ffmpeg error"),
            "/tmp/ok.webm",
        ]
        results = pipe.run_pipeline(provider="openai", limit=2)
        assert results[0]["status"] == "failed"
        assert "Render failed" in results[0]["error"]
        assert results[1]["status"] == "done"

    @patch("manimator.pipeline.Pipeline._generate_one")
    @patch("manimator.pipeline.Pipeline._render_one")
    @patch("manimator.pipeline.Pipeline._upload_one")
    def test_upload_failure_records_error(self, mock_upload, mock_render, mock_gen, pipe, sample_topics):
        """Upload failure is recorded; video still exists on disk."""
        pipe.add_topics(sample_topics[:1])
        mock_gen.return_value = {"meta": {"title": "T"}, "scenes": []}
        mock_render.return_value = "/tmp/ok.webm"
        mock_upload.side_effect = RuntimeError("YouTube quota exceeded")
        results = pipe.run_pipeline(provider="openai", limit=1, upload=True)
        assert results[0]["status"] == "failed"
        assert "quota" in results[0]["error"].lower()


class TestEmptyQueue:
    @patch("manimator.pipeline.Pipeline._generate_one")
    @patch("manimator.pipeline.Pipeline._render_one")
    def test_empty_queue_returns_empty(self, mock_render, mock_gen, pipe):
        """Running pipeline with no topics returns empty list, no errors."""
        results = pipe.run_pipeline(provider="openai", limit=5)
        assert results == []
        mock_gen.assert_not_called()
        mock_render.assert_not_called()


class TestStaleRecovery:
    def test_recovers_stale_generating(self, pipe):
        """Videos stuck in 'generating' for >15 min get marked failed."""
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, 'generating', ?)",
            ("v1", "stale topic", stale_time),
        )
        pipe._conn.commit()

        count = pipe.recover_stale()
        assert count == 1
        v = pipe.get_video("v1")
        assert v["status"] == "failed"
        assert "stale" in v["error"].lower()

    def test_does_not_recover_recent(self, pipe):
        """Videos in transient state for <15 min are left alone."""
        recent = datetime.now(timezone.utc).isoformat()
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, 'rendering', ?)",
            ("v2", "recent topic", recent),
        )
        pipe._conn.commit()

        count = pipe.recover_stale()
        assert count == 0
        v = pipe.get_video("v2")
        assert v["status"] == "rendering"

    def test_does_not_touch_done_or_failed(self, pipe):
        """Done and failed videos are never recovered."""
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, 'done', ?)",
            ("v3", "done topic", stale_time),
        )
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, created_at) VALUES (?, ?, 'failed', ?)",
            ("v4", "failed topic", stale_time),
        )
        pipe._conn.commit()

        count = pipe.recover_stale()
        assert count == 0


class TestUploadQuota:
    def test_quota_check_passes_when_under_limit(self, pipe):
        """No error when uploads today < limit."""
        pipe._check_quota()  # Should not raise

    def test_quota_check_raises_at_limit(self, pipe):
        """RuntimeError when daily upload limit reached."""
        today = datetime.now(timezone.utc).date().isoformat()
        for i in range(6):
            pipe._conn.execute(
                "INSERT INTO videos (id, topic, status, youtube_id, created_at, completed_at) "
                "VALUES (?, ?, 'done', ?, ?, ?)",
                (f"v{i}", f"t{i}", f"yt_{i}", today, today),
            )
        pipe._conn.commit()

        with pytest.raises(RuntimeError, match="quota"):
            pipe._check_quota()

    def test_uploads_today_counts_correctly(self, pipe):
        today = datetime.now(timezone.utc).date().isoformat()
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        # Today's upload
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, youtube_id, created_at, completed_at) "
            "VALUES (?, ?, 'done', ?, ?, ?)",
            ("v1", "t1", "yt_1", today, today),
        )
        # Yesterday's upload — should not count
        pipe._conn.execute(
            "INSERT INTO videos (id, topic, status, youtube_id, created_at, completed_at) "
            "VALUES (?, ?, 'done', ?, ?, ?)",
            ("v2", "t2", "yt_2", yesterday, yesterday),
        )
        pipe._conn.commit()
        assert pipe._uploads_today() == 1


class TestRetryFailed:
    def test_resets_failed_to_queued(self, pipe):
        now = "2026-01-01T00:00:00"
        for i in range(3):
            pipe._conn.execute(
                "INSERT INTO videos (id, topic, status, error, created_at) VALUES (?, ?, 'failed', 'err', ?)",
                (f"v{i}", f"t{i}", now),
            )
        pipe._conn.commit()

        count = pipe.retry_failed(limit=2)
        assert count == 2
        status = pipe.get_status()
        assert status["failed"] == 1
        assert status["queued"] == 2
