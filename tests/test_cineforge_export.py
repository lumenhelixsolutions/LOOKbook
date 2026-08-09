"""Tests for lookBOOK → CineForge export bridge."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lookbook.pipeline.cineforge_export import (
    CINEFORGE_EXPORT_SCHEMA,
    CineforgeIngestError,
    export_cineforge,
    export_cineforge_file,
    prepare_cineforge_payload,
    push_cineforge_ingest,
)


@pytest.fixture
def project_with_shots(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    analysis = project / "analysis"
    analysis.mkdir(parents=True)
    shot_data = {
        "schema": "lookbook.shot_graph.v0.3",
        "total_shots": 2,
        "total_duration_seconds": 7.0,
        "fps": 24,
        "shots": [
            {
                "shot_index": 0,
                "scene_index": 0,
                "type": "establishing",
                "duration_seconds": 4.0,
                "camera": "pan right",
                "characters": ["Hero"],
                "motion_directive": "Hero leaps forward.",
                "panels": [0],
            },
            {
                "shot_index": 1,
                "scene_index": 0,
                "type": "dialogue",
                "duration_seconds": 3.0,
                "camera": "static",
                "characters": ["Hero", "Villain"],
                "dialogue": ["You won't escape!"],
                "panels": [1],
            },
        ],
    }
    (analysis / "shot_graph.json").write_text(json.dumps(shot_data), encoding="utf-8")
    return project


def test_prepare_payload_from_fixture(project_with_shots: Path) -> None:
    ingest_body, graph_path, rel_path = prepare_cineforge_payload(project_with_shots)
    assert graph_path.name == "shot_graph.json"
    assert rel_path == "analysis/shot_graph.json"
    assert len(ingest_body["shot_graph"]["shots"]) == 2
    assert ingest_body["replace_existing_shots"] is True
    assert ingest_body["shot_graph"]["schema"] == "lookbook.shot_graph.v0.3"
    assert "choreography" not in ingest_body
    assert "panels" not in ingest_body


def test_prepare_payload_includes_choreography_when_present(project_with_shots: Path) -> None:
    analysis = project_with_shots / "analysis"
    choreography = {
        "schema": "lookbook.choreography.v0.1",
        "total_lines": 1,
        "lines": [
            {
                "line_index": 0,
                "speaker": "Hero",
                "text": "You won't escape!",
                "classification": "dialogue",
                "panel_index": 1,
            }
        ],
        "voice_cast": {},
    }
    panels = {
        "schema": "lookbook.panels.v0.3",
        "panels": [
            {"panel_index": 0, "bbox": {"x": 0, "y": 0, "w": 100, "h": 100}},
            {"panel_index": 1, "bbox": {"x": 100, "y": 0, "w": 100, "h": 100}},
        ],
    }
    (analysis / "choreography.json").write_text(json.dumps(choreography), encoding="utf-8")
    (analysis / "panel_analysis.json").write_text(json.dumps(panels), encoding="utf-8")

    ingest_body, _, _ = prepare_cineforge_payload(project_with_shots)
    assert ingest_body["choreography"]["schema"] == "lookbook.choreography.v0.1"
    assert len(ingest_body["choreography"]["lines"]) == 1
    assert len(ingest_body["panels"]) == 2

    result = export_cineforge_file(project_with_shots)
    wrapper = json.loads(result["output_path"].read_text(encoding="utf-8"))
    assert wrapper["choreography"]["total_lines"] == 1
    assert len(wrapper["panels"]) == 2


def test_export_writes_file(project_with_shots: Path) -> None:
    result = export_cineforge_file(project_with_shots)
    out_path = result["output_path"]
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["schema"] == CINEFORGE_EXPORT_SCHEMA
    assert data["shot_graph_path"] == "analysis/shot_graph.json"
    assert len(data["shot_graph"]["shots"]) == 2
    assert result["shot_count"] == 2


def test_rejects_empty_shots(tmp_path: Path) -> None:
    project = tmp_path / "empty"
    analysis = project / "analysis"
    analysis.mkdir(parents=True)
    (analysis / "shot_graph.json").write_text(
        json.dumps({"schema": "lookbook.shot_graph.v0.3", "shots": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="at least one shot"):
        prepare_cineforge_payload(project)


def test_push_mock_success(project_with_shots: Path) -> None:
    ingest_body, _, _ = prepare_cineforge_payload(project_with_shots)
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(
        {"shot_count": 2, "treatment_id": "t-1", "source": "lookbook"}
    ).encode("utf-8")
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as urlopen:
        response = push_cineforge_ingest(
            ingest_body,
            "http://127.0.0.1:8000",
            "proj-uuid-123",
        )

    assert response["shot_count"] == 2
    urlopen.assert_called_once()
    req = urlopen.call_args[0][0]
    assert req.full_url.endswith("/projects/proj-uuid-123/ingest/lookbook")
    assert req.method == "POST"


def test_push_mock_404(project_with_shots: Path) -> None:
    import urllib.error

    ingest_body, _, _ = prepare_cineforge_payload(project_with_shots)
    err = urllib.error.HTTPError(
        url="http://127.0.0.1:8000/projects/missing/ingest/lookbook",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=MagicMock(read=MagicMock(return_value=b'{"detail":"Project not found"}')),
    )

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(CineforgeIngestError, match="404") as exc_info:
            push_cineforge_ingest(ingest_body, "http://127.0.0.1:8000", "missing")

    assert exc_info.value.status_code == 404


def test_export_with_push_flag(project_with_shots: Path) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"shot_count": 2}).encode("utf-8")
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = export_cineforge(
            project_with_shots,
            push=True,
            cineforge_url="http://127.0.0.1:8000",
            project_id="cf-1",
        )

    assert result["pushed"] is True
    assert result["output_path"].exists()
    assert result["ingest_response"]["shot_count"] == 2