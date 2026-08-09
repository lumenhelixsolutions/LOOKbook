"""End-to-end CLI workflow test.

Exercises the full happy path through the lookBOOK CLI:
init → analyze-source → detect-panels → build-scene-graph → build-shot-graph → generate-animatic.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw

from lookbook.cli import main
from lookbook.video.animatic import _MOVIEPY, _resolve_font


def _create_comic_image(path: Path) -> Path:
    """Generate a simple comic page with bordered panels for contour detection."""
    img = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 380, 280], outline="black", width=8)
    draw.rectangle([420, 20, 780, 280], outline="black", width=8)
    draw.rectangle([20, 320, 780, 580], outline="black", width=8)
    img.save(path)
    return path


class TestE2ECLI:
    @patch("lookbook.pipeline.vision_llm.get_analyzer")
    def test_full_happy_path(self, mock_get_analyzer, tmp_path: Path):
        """Run the complete lookBOOK CLI workflow and verify artifacts at each stage."""
        project = tmp_path / "test_project"
        image = tmp_path / "comic.png"
        _create_comic_image(image)

        # 1. init project
        main(["init", str(project), "--name", "test_project"])
        assert (project / "manifest.json").exists()
        manifest = json.loads((project / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["project"] == "test_project"

        # 2. analyze source (classical scaffold — no real LLM calls)
        main(["analyze-source", str(image), str(project)])
        analysis_path = project / "analysis" / "source_analysis.json"
        assert analysis_path.exists()
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert analysis["source_file"] == "comic.png"
        assert analysis["image"]["width"] == 800
        assert analysis["image"]["height"] == 600

        # 3. detect panels
        source_copy = project / "source" / "comic.png"
        main(["detect-panels", str(source_copy), str(project)])
        panel_path = project / "analysis" / "panel_analysis.json"
        assert panel_path.exists()
        panel_data = json.loads(panel_path.read_text(encoding="utf-8"))
        assert panel_data["total_panels"] >= 1

        # 4. build scene graph
        main(["build-scene-graph", str(project)])
        scene_path = project / "analysis" / "scene_graph.json"
        assert scene_path.exists()
        scene_data = json.loads(scene_path.read_text(encoding="utf-8"))
        assert scene_data["total_scenes"] >= 1

        # 5. build shot graph
        main(["build-shot-graph", str(project)])
        shot_path = project / "analysis" / "shot_graph.json"
        assert shot_path.exists()
        shot_data = json.loads(shot_path.read_text(encoding="utf-8"))
        assert shot_data["total_shots"] >= 1
        assert len(shot_data["shots"]) >= 1

        # 6. generate animatic
        if not _MOVIEPY or _resolve_font() is None:
            pytest.skip("moviepy or system font required for animatic generation")

        output = tmp_path / "animatic.mp4"
        main([
            "generate-animatic",
            str(shot_path),
            "--output", str(output),
            "--duration", "1.0",
            "--width", "320",
            "--height", "180",
            "--fps", "12",
        ])
        assert output.exists()
        assert output.stat().st_size > 0

        # Ensure no vision LLM calls leaked through
        mock_get_analyzer.assert_not_called()
