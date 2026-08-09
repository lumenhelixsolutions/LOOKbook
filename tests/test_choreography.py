from __future__ import annotations

import json
from pathlib import Path

import pytest

from lookbook.pipeline.choreography import build_choreography, camera_for_line
from lookbook.pipeline.living_panels_export import export_living_panels
from lookbook.pipeline.shot_graph import build_shot_graph


@pytest.fixture
def choreo_project(tmp_path: Path) -> Path:
    project = tmp_path / "choreo_project"
    (project / "analysis").mkdir(parents=True)
    (project / "source").mkdir()

    panels = {
        "schema": "lookbook.panels.v0.2",
        "panels": [
            {
                "panel_index": 0,
                "bbox": {"x": 0, "y": 0, "w": 200, "h": 300},
                "image_path": "analysis/panels/panel_000.png",
            },
            {
                "panel_index": 1,
                "bbox": {"x": 200, "y": 0, "w": 200, "h": 300},
                "image_path": "analysis/panels/panel_001.png",
            },
        ],
    }
    (project / "analysis" / "panel_analysis.json").write_text(json.dumps(panels), encoding="utf-8")
    (project / "analysis" / "panels").mkdir(parents=True, exist_ok=True)
    (project / "analysis" / "panels" / "panel_000.png").write_bytes(b"png")
    (project / "analysis" / "panels" / "panel_001.png").write_bytes(b"png")

    ocr = {
        "schema": "lookbook.ocr.v0.2",
        "blocks": [
            {
                "text": '"Hello from the left."',
                "classification": "dialogue",
                "bbox": {"x": 40, "y": 80, "w": 120, "h": 40},
            },
            {
                "text": '"Reply from the right."',
                "classification": "dialogue",
                "bbox": {"x": 260, "y": 90, "w": 120, "h": 40},
            },
            {
                "text": "NARRATOR: Meanwhile…",
                "classification": "narration",
                "bbox": {"x": 30, "y": 220, "w": 140, "h": 30},
            },
        ],
    }
    (project / "analysis" / "ocr_result.json").write_text(json.dumps(ocr), encoding="utf-8")

    characters = {
        "schema": "lookbook.characters.v0.2",
        "characters": [
            {
                "character_id": "char_000",
                "name": "Hero",
                "appearances": 1,
                "panels": [{"panel_index": 0, "bbox": {"x": 20, "y": 120, "w": 80, "h": 120}}],
            },
            {
                "character_id": "char_001",
                "name": "Rival",
                "appearances": 1,
                "panels": [{"panel_index": 1, "bbox": {"x": 240, "y": 130, "w": 80, "h": 120}}],
            },
        ],
    }
    (project / "analysis" / "character_analysis.json").write_text(json.dumps(characters), encoding="utf-8")

    scenes = {
        "schema": "lookbook.scene_graph.v0.2",
        "total_scenes": 1,
        "scenes": [
            {
                "scene_index": 0,
                "panel_count": 2,
                "panel_indices": [0, 1],
                "panels": [
                    {"panel_index": 0, "bbox": {"x": 0, "y": 0, "w": 200, "h": 300}},
                    {"panel_index": 1, "bbox": {"x": 200, "y": 0, "w": 200, "h": 300}},
                ],
                "characters": ["char_000", "char_001"],
                "dialogue": ['"Hello from the left."', '"Reply from the right."'],
                "narration": [],
            }
        ],
    }
    (project / "analysis" / "scene_graph.json").write_text(json.dumps(scenes), encoding="utf-8")
    return project


class TestChoreography:
    def test_build_choreography_links_speakers_and_panels(self, choreo_project: Path):
        lines = build_choreography(choreo_project)
        assert len(lines) == 3
        assert lines[0]["panel_index"] == 0
        assert lines[0]["speaker"] == "Hero"
        assert lines[1]["panel_index"] == 1
        assert lines[1]["speaker"] == "Rival"
        assert lines[2]["speaker"] == "narrator"

        out = choreo_project / "analysis" / "choreography.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["schema"] == "lookbook.choreography.v0.1"
        assert "voice_cast" in data

    def test_camera_for_line_positions(self):
        left = camera_for_line(
            {"classification": "dialogue", "bubble_bbox": {"x": 10, "w": 40}},
            {"w": 200},
        )
        right = camera_for_line(
            {"classification": "dialogue", "bubble_bbox": {"x": 150, "w": 40}},
            {"w": 200},
        )
        center = camera_for_line(
            {"classification": "dialogue", "bubble_bbox": {"x": 80, "w": 40}},
            {"w": 200},
        )
        assert left == "track right"
        assert right == "track left"
        assert center == "push in"

    def test_shot_graph_uses_choreography_camera(self, choreo_project: Path):
        build_choreography(choreo_project)
        shots = build_shot_graph(choreo_project)
        assert shots
        assert shots[0]["camera"] in ("track right", "track left", "push in")
        assert shots[0].get("active_speaker") in ("Hero", "Rival", "unknown")

    def test_shot_graph_one_shot_per_choreography_line(self, choreo_project: Path):
        lines = build_choreography(choreo_project)
        shots = build_shot_graph(choreo_project)

        assert len(shots) == len(lines) == 3

        for shot, line in zip(shots, lines):
            assert shot["choreography_line_index"] == line["line_index"]
            assert shot["active_speaker"] == line["speaker"]
            assert shot["panel"] == line["panel_index"]
            assert shot["panels"] == [line["panel_index"]]
            assert shot["duration_seconds"] >= 2.0
            assert shot["duration_seconds"] == round(max(2.0, line["word_count"] / 3.0), 1)

        assert shots[0]["camera"] == "push in"
        assert shots[1]["camera"] == "track left"
        assert shots[2]["camera"] == "crane up"
        assert shots[0]["transition_in"] == "cut"
        assert shots[1]["transition_in"] == "dissolve"
        assert shots[2]["transition_in"] == "dissolve"

    def test_export_living_panels_html(self, choreo_project: Path):
        build_choreography(choreo_project)
        build_shot_graph(choreo_project)
        out = export_living_panels(choreo_project)
        assert out.exists()
        html = out.read_text(encoding="utf-8")
        assert "living panels" in html.lower()
        assert "lookbook-data" in html
        assert "Hello from the left" in html