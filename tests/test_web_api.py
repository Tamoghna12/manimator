"""Tests for manimator.web.app — Flask API routes."""

import json
from unittest.mock import patch, MagicMock


class TestIndexRoute:
    def test_get_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200


class TestTemplatesRoute:
    def test_get_templates_returns_json(self, client):
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "structures" in data
        assert "domains" in data
        assert "scene_types" in data

    def test_structures_is_non_empty(self, client):
        data = client.get("/api/templates").get_json()
        assert len(data["structures"]) > 0

    def test_scene_types_is_non_empty(self, client):
        data = client.get("/api/templates").get_json()
        assert len(data["scene_types"]) > 0


class TestValidateRoute:
    def test_valid_storyboard_returns_valid_true(self, client, valid_storyboard_dict):
        resp = client.post(
            "/api/validate",
            data=json.dumps(valid_storyboard_dict),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True
        assert data["scenes"] == 3

    def test_invalid_storyboard_returns_400(self, client, storyboard_invalid_scene_type):
        resp = client.post(
            "/api/validate",
            data=json.dumps(storyboard_invalid_scene_type),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["valid"] is False

    def test_missing_meta_returns_400(self, client, storyboard_missing_meta):
        resp = client.post(
            "/api/validate",
            data=json.dumps(storyboard_missing_meta),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestPreviewSceneRoute:
    def test_preview_returns_html(self, client):
        payload = {
            "scene": {
                "type": "title",
                "id": "t",
                "title": "Preview Test",
                "subtitle": "Sub",
            },
            "theme": "wong",
        }
        resp = client.post(
            "/api/preview_scene",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "html" in data
        assert len(data["html"]) > 0

    def test_unknown_scene_type_returns_400(self, client):
        payload = {
            "scene": {"type": "does_not_exist", "id": "x"},
            "theme": "wong",
        }
        resp = client.post(
            "/api/preview_scene",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ── Upload route tests ────────────────────────────────────────────────────────


class TestUploadRoute:
    def test_upload_invalid_job_id(self, client):
        resp = client.post(
            "/api/upload",
            data=json.dumps({"job_id": "INVALID!", "privacy": "private"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_upload_invalid_privacy(self, client):
        resp = client.post(
            "/api/upload",
            data=json.dumps({"job_id": "abcd1234", "privacy": "bogus"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_upload_nonexistent_job(self, client):
        resp = client.post(
            "/api/upload",
            data=json.dumps({"job_id": "abcd1234", "privacy": "private"}),
            content_type="application/json",
        )
        assert resp.status_code == 404


# ── Pipeline route tests ─────────────────────────────────────────────────────


class TestPipelineStatusRoute:
    @patch("manimator.web.app._get_pipeline")
    def test_returns_status_dict(self, mock_get, client):
        mock_pipe = MagicMock()
        mock_pipe.get_status.return_value = {
            "queued": 3, "generating": 0, "rendering": 0,
            "uploading": 0, "done": 5, "failed": 1, "total": 9,
        }
        mock_get.return_value = mock_pipe
        resp = client.get("/api/pipeline/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 9
        assert data["done"] == 5


class TestPipelineVideosRoute:
    @patch("manimator.web.app._get_pipeline")
    def test_returns_video_list(self, mock_get, client):
        mock_pipe = MagicMock()
        mock_pipe.list_videos.return_value = [
            {"id": "v1", "topic": "CRISPR", "status": "done"},
        ]
        mock_get.return_value = mock_pipe
        resp = client.get("/api/pipeline/videos")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["topic"] == "CRISPR"

    @patch("manimator.web.app._get_pipeline")
    def test_status_filter_passed(self, mock_get, client):
        mock_pipe = MagicMock()
        mock_pipe.list_videos.return_value = []
        mock_get.return_value = mock_pipe
        client.get("/api/pipeline/videos?status=done&limit=5")
        mock_pipe.list_videos.assert_called_once_with(status="done", limit=5)


class TestPipelineAddTopicsRoute:
    @patch("manimator.web.app._get_pipeline")
    def test_add_topics_returns_ids(self, mock_get, client):
        mock_pipe = MagicMock()
        mock_pipe.add_topics.return_value = ["id1", "id2"]
        mock_get.return_value = mock_pipe
        resp = client.post(
            "/api/pipeline/add-topics",
            data=json.dumps({"topics": [
                {"topic": "CRISPR"}, {"topic": "Quantum"},
            ]}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["added"] == 2

    def test_add_topics_empty_returns_400(self, client):
        resp = client.post(
            "/api/pipeline/add-topics",
            data=json.dumps({"topics": []}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_add_topics_missing_topic_key_returns_400(self, client):
        resp = client.post(
            "/api/pipeline/add-topics",
            data=json.dumps({"topics": [{"domain": "biology_reel"}]}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestPipelineAddStoryboardsRoute:
    @patch("manimator.web.app._get_pipeline")
    def test_add_storyboards_returns_ids(self, mock_get, client, valid_storyboard_dict):
        mock_pipe = MagicMock()
        mock_pipe.add_storyboards.return_value = ["id1"]
        mock_get.return_value = mock_pipe
        resp = client.post(
            "/api/pipeline/add-storyboards",
            data=json.dumps({"storyboards": [{"storyboard": valid_storyboard_dict}]}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["added"] == 1

    def test_empty_storyboards_returns_400(self, client):
        resp = client.post(
            "/api/pipeline/add-storyboards",
            data=json.dumps({"storyboards": []}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_invalid_storyboard_returns_400(self, client):
        resp = client.post(
            "/api/pipeline/add-storyboards",
            data=json.dumps({"storyboards": [{"storyboard": {"no_meta": True}}]}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestPipelineRenderRoute:
    @patch("manimator.web.app._get_pipeline")
    @patch("manimator.web.app._render_pool")
    def test_render_returns_started(self, mock_pool, mock_get, client):
        mock_pipe = MagicMock()
        mock_get.return_value = mock_pipe
        resp = client.post(
            "/api/pipeline/render",
            data=json.dumps({"limit": 3}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "started"
        assert data["limit"] == 3


class TestPipelineRunRoute:
    def test_run_without_api_key_returns_400(self, client):
        resp = client.post(
            "/api/pipeline/run",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "API key" in resp.get_json()["error"]

    @patch("manimator.web.app._get_pipeline")
    @patch("manimator.web.app._render_pool")
    def test_run_with_key_returns_started(self, mock_pool, mock_get, client):
        mock_pipe = MagicMock()
        mock_get.return_value = mock_pipe
        resp = client.post(
            "/api/pipeline/run",
            data=json.dumps({"provider": "openai", "api_key": "sk-test", "limit": 2}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "started"
        assert data["limit"] == 2


# ── Analytics route tests ────────────────────────────────────────────────────


class TestAnalyticsSummaryRoute:
    @patch("manimator.web.app._get_analytics")
    def test_returns_insights(self, mock_get, client):
        mock_anl = MagicMock()
        mock_anl.get_insights.return_value = {
            "total_videos": 10, "total_views": 5000,
            "avg_views_per_video": 500, "best_domain": "biology_reel",
            "worst_domain": "cs_reel", "best_video": None,
            "best_posting_day": "Tuesday", "avg_ctr": 0.22,
            "data_freshness": "2026-03-15T00:00:00",
        }
        mock_get.return_value = mock_anl
        resp = client.get("/api/analytics/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_views"] == 5000
        assert data["best_domain"] == "biology_reel"


class TestAnalyticsTopRoute:
    @patch("manimator.web.app._get_analytics")
    def test_returns_top_list(self, mock_get, client):
        mock_anl = MagicMock()
        mock_anl.get_top_videos.return_value = [
            {"video_id": "v1", "total_views": 300, "topic": "CRISPR"},
        ]
        mock_get.return_value = mock_anl
        resp = client.get("/api/analytics/top?metric=views&limit=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        mock_anl.get_top_videos.assert_called_once_with(metric="views", limit=5, days=30)

    @patch("manimator.web.app._get_analytics")
    def test_invalid_metric_returns_400(self, mock_get, client):
        mock_anl = MagicMock()
        mock_anl.get_top_videos.side_effect = ValueError("Invalid metric")
        mock_get.return_value = mock_anl
        resp = client.get("/api/analytics/top?metric=subscribers")
        assert resp.status_code == 400


class TestAnalyticsSyncRoute:
    @patch("manimator.web.app._get_analytics")
    def test_sync_returns_count(self, mock_get, client):
        mock_anl = MagicMock()
        mock_anl.sync_metrics.return_value = 42
        mock_get.return_value = mock_anl
        resp = client.post(
            "/api/analytics/sync",
            data=json.dumps({"days": 14}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["synced"] == 42
        mock_anl.sync_metrics.assert_called_once_with(days=14)

    @patch("manimator.web.app._get_analytics")
    def test_sync_failure_returns_500(self, mock_get, client):
        mock_anl = MagicMock()
        mock_anl.sync_metrics.side_effect = RuntimeError("API down")
        mock_get.return_value = mock_anl
        resp = client.post(
            "/api/analytics/sync",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 500
