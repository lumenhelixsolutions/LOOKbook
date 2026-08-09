"""Unit smokes for lookBOOK director-graph (M17)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DIRECTOR_GRAPH = Path(__file__).resolve().parents[1] / "director-graph"
LOOKBOOK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTOR_GRAPH))
sys.path.insert(0, str(LOOKBOOK_ROOT))

from runner import build_graph, invoke_graph, load_graph_profiles  # noqa: E402


@pytest.fixture
def mini_project(tmp_path: Path) -> Path:
    project = tmp_path / "director_graph_demo"
    (project / "analysis").mkdir(parents=True)
    shot_graph = {
        "schema": "lookbook.shot_graph.v0.3",
        "shots": [
            {
                "shot_index": 0,
                "scene_index": 0,
                "type": "establishing",
                "duration_seconds": 4.0,
                "camera": "pan right",
                "characters": ["Hero"],
                "motion_directive": "Hero enters.",
                "panels": [0],
            }
        ],
    }
    (project / "analysis" / "shot_graph.json").write_text(json.dumps(shot_graph), encoding="utf-8")
    return project


def test_graph_profiles_load():
    doc = load_graph_profiles()
    assert "classical-runway" in doc.get("profiles", {})


def test_build_graph_compiles():
    assert build_graph() is not None


def test_invoke_graph_dry_run(mini_project: Path):
    result = invoke_graph(
        "dry-run-audit",
        project_path=str(mini_project),
        dry_run_mode=True,
        auto_approve=True,
    )
    assert result["ok"] is True
    assert result["dry_run_mode"] is True
    assert result["state"]["review_summary"]["shot_count"] == 1


def test_graph_spec_present():
    spec = json.loads((DIRECTOR_GRAPH / "graph.spec.json").read_text(encoding="utf-8"))
    assert spec["name"] == "lookbook-director-pipeline"