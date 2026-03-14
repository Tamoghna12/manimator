"""Tests for manimator.web.app — Flask API routes."""

import json


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
