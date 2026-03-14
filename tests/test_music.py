"""Tests for manimator.music — background music module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from manimator.music import (
    MUSIC_PRESETS,
    ensure_music_asset,
)


class TestMusicPresets:
    def test_three_presets_exist(self):
        assert "ambient" in MUSIC_PRESETS
        assert "corporate" in MUSIC_PRESETS
        assert "cinematic" in MUSIC_PRESETS

    def test_preset_has_required_keys(self):
        for name, info in MUSIC_PRESETS.items():
            assert "filename" in info, f"{name} missing filename"
            assert "ffmpeg_filter" in info, f"{name} missing ffmpeg_filter"
            assert "description" in info, f"{name} missing description"
            assert info["filename"].endswith(".mp3"), f"{name} filename not MP3"


class TestEnsureMusicAsset:
    def test_local_file_path_returned(self, tmp_path):
        mp3 = tmp_path / "my_track.mp3"
        mp3.write_bytes(b"\x00" * 2048)
        result = ensure_music_asset(str(mp3))
        assert result == mp3

    def test_unknown_preset_no_file_raises(self):
        with pytest.raises(FileNotFoundError, match="Unknown music preset"):
            ensure_music_asset("nonexistent_preset_xyz")

    def test_cached_file_returned_without_download(self, tmp_path):
        with patch("manimator.music.CACHE_DIR", tmp_path):
            cached = tmp_path / "ambient_loop.mp3"
            cached.write_bytes(b"\x00" * 2048)
            result = ensure_music_asset("ambient")
            assert result == cached
