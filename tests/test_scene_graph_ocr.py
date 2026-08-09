"""Regression: scene graph must read OCR from ocr_result.json."""

import json
from pathlib import Path

from lookbook.pipeline.scene_graph import build_scene_graph


def test_scene_graph_attaches_ocr_dialogue(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    analysis = project / "analysis"
    analysis.mkdir(parents=True)

    (analysis / "panel_analysis.json").write_text(
        json.dumps(
            {
                "panels": [
                    {
                        "panel_index": 0,
                        "bbox": {"x": 0, "y": 0, "w": 200, "h": 200},
                        "area": 40000,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (analysis / "ocr_result.json").write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "text": '"Hello there!"',
                        "classification": "dialogue",
                        "bbox": {"x": 20, "y": 30, "w": 80, "h": 40},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (analysis / "character_analysis.json").write_text(
        json.dumps({"characters": []}),
        encoding="utf-8",
    )

    scenes = build_scene_graph(project)
    assert scenes[0]["dialogue"] == ['"Hello there!"']