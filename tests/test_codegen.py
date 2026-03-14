"""Tests for manimator.codegen — Python code generation from storyboards."""

import tempfile
from pathlib import Path

from manimator.schema import Storyboard
from manimator.codegen import generate


class TestGenerate:
    """Verify that generate() produces valid Python with correct class names."""

    def _make_storyboard(self):
        return Storyboard(
            meta={"title": "Test", "color_theme": "wong", "format": "presentation"},
            scenes=[
                {"type": "title", "id": "intro", "title": "Hello"},
                {"type": "bullet_list", "id": "points", "header": "Items",
                 "items": ["A", "B"]},
                {"type": "closing", "id": "end"},
            ],
        )

    def test_returns_list_of_class_names(self):
        sb = self._make_storyboard()
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            path = Path(f.name)
        class_names = generate(sb, path)
        assert isinstance(class_names, list)
        assert len(class_names) == 3
        path.unlink(missing_ok=True)

    def test_class_names_match_scene_ids(self):
        sb = self._make_storyboard()
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            path = Path(f.name)
        class_names = generate(sb, path)
        assert class_names[0] == "S00_intro"
        assert class_names[1] == "S01_points"
        assert class_names[2] == "S02_end"
        path.unlink(missing_ok=True)

    def test_output_is_valid_python(self):
        sb = self._make_storyboard()
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            path = Path(f.name)
        generate(sb, path)
        code = path.read_text()
        # compile() will raise SyntaxError if the code is not valid Python
        compile(code, str(path), "exec")
        path.unlink(missing_ok=True)

    def test_output_contains_class_definitions(self):
        sb = self._make_storyboard()
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            path = Path(f.name)
        generate(sb, path)
        code = path.read_text()
        assert "class S00_intro(Scene):" in code
        assert "class S01_points(Scene):" in code
        assert "class S02_end(Scene):" in code
        path.unlink(missing_ok=True)

    def test_output_contains_theme_setup(self):
        sb = self._make_storyboard()
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            path = Path(f.name)
        generate(sb, path)
        code = path.read_text()
        assert "set_theme('wong')" in code
        path.unlink(missing_ok=True)
