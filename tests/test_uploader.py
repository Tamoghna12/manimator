"""Tests for manimator.uploader — YouTube upload functionality."""

import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── Mock Google SDK modules before importing uploader ─────────────────────────
# These packages may not be installed in the test environment.

def _ensure_google_mocks():
    """Install mock modules for Google SDK if not already available."""
    mods = {}
    for name in [
        "google", "google.oauth2", "google.oauth2.credentials",
        "google.auth", "google.auth.transport", "google.auth.transport.requests",
        "google_auth_oauthlib", "google_auth_oauthlib.flow",
        "googleapiclient", "googleapiclient.discovery", "googleapiclient.http",
    ]:
        if name not in sys.modules:
            mods[name] = types.ModuleType(name)
            sys.modules[name] = mods[name]

    # Attach required attributes
    sys.modules["google.oauth2.credentials"].Credentials = MagicMock()
    sys.modules["google_auth_oauthlib.flow"].InstalledAppFlow = MagicMock()
    sys.modules["googleapiclient.discovery"].build = MagicMock()
    sys.modules["googleapiclient.http"].MediaFileUpload = MagicMock()


_ensure_google_mocks()

from manimator.uploader import upload_video, upload_short, _get_credentials


class TestUploadVideo:
    @patch("manimator.uploader._build_youtube_service")
    def test_returns_video_id_and_url(self, mock_service):
        """Successful upload returns video_id, url, status."""
        mock_yt = MagicMock()
        mock_service.return_value = mock_yt

        mock_insert = MagicMock()
        mock_yt.videos.return_value.insert.return_value = mock_insert
        mock_insert.next_chunk.return_value = (
            None,
            {"id": "abc123", "status": {"uploadStatus": "uploaded"}},
        )

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(b"fake video data")
            video_path = f.name

        try:
            result = upload_video(video_path, title="Test Video", description="desc")
            assert result["video_id"] == "abc123"
            assert "abc123" in result["url"]
            assert result["status"] == "uploaded"
        finally:
            Path(video_path).unlink()

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            upload_video("/nonexistent/video.webm", title="Test")

    def test_invalid_privacy(self):
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(b"data")
            video_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid privacy"):
                upload_video(video_path, title="Test", privacy="invalid")
        finally:
            Path(video_path).unlink()

    @patch("manimator.uploader._build_youtube_service")
    def test_title_truncated(self, mock_service):
        """Titles longer than 100 chars are truncated."""
        mock_yt = MagicMock()
        mock_service.return_value = mock_yt
        mock_insert = MagicMock()
        mock_yt.videos.return_value.insert.return_value = mock_insert
        mock_insert.next_chunk.return_value = (
            None, {"id": "x", "status": {"uploadStatus": "uploaded"}}
        )

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(b"data")
            video_path = f.name

        try:
            long_title = "A" * 200
            upload_video(video_path, title=long_title)
            # Verify the body passed to insert has truncated title
            call_kwargs = mock_yt.videos.return_value.insert.call_args
            body = call_kwargs[1]["body"] if "body" in call_kwargs[1] else call_kwargs[0][0]
            assert len(body["snippet"]["title"]) == 100
        finally:
            Path(video_path).unlink()


class TestUploadShort:
    @patch("manimator.uploader.upload_video")
    @patch("manimator.renderer.generate_thumbnail")
    @patch("manimator.social.generate_post_copy")
    def test_shorts_in_description(self, mock_copy, mock_thumb, mock_upload):
        """#Shorts is prepended to the description."""
        mock_copy.return_value = {
            "hook_text": "Did you know?",
            "caption": "Amazing science content",
            "hashtags": ["#science", "#education"],
        }
        mock_thumb.return_value = None
        mock_upload.return_value = {"video_id": "x", "url": "http://yt/x", "status": "uploaded"}

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(b"data")
            video_path = f.name

        try:
            result = upload_short(
                video_path=video_path,
                storyboard_data={"meta": {"title": "Test"}, "scenes": []},
            )
            # Check description passed to upload_video starts with #Shorts
            call_kwargs = mock_upload.call_args[1]
            assert call_kwargs["description"].startswith("#Shorts")
            assert result["video_id"] == "x"
        finally:
            Path(video_path).unlink()

    @patch("manimator.uploader.upload_video")
    @patch("manimator.renderer.generate_thumbnail")
    @patch("manimator.social.generate_post_copy")
    def test_title_within_limit(self, mock_copy, mock_thumb, mock_upload):
        """Title from hook_text is truncated to 100 chars."""
        mock_copy.return_value = {
            "hook_text": "X" * 200,
            "caption": "content",
            "hashtags": [],
        }
        mock_thumb.return_value = None
        mock_upload.return_value = {"video_id": "y", "url": "http://yt/y", "status": "uploaded"}

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(b"data")
            video_path = f.name

        try:
            upload_short(video_path, {"meta": {"title": "T"}, "scenes": []})
            call_kwargs = mock_upload.call_args[1]
            assert len(call_kwargs["title"]) <= 100
        finally:
            Path(video_path).unlink()


class TestCredentials:
    def test_missing_client_secret_raises(self):
        """FileNotFoundError when client_secret.json is absent."""
        with patch("manimator.uploader.CLIENT_SECRET_PATH", Path("/nonexistent/client_secret.json")):
            with patch("manimator.uploader.TOKEN_PATH", Path("/nonexistent/token.json")):
                with pytest.raises(FileNotFoundError, match="client secret"):
                    _get_credentials()
