"""Thin wrappers around lookBOOK pipeline modules for director graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def resolve_project(project: str | Path) -> Path:
    path = Path(project)
    if not path.exists():
        raise FileNotFoundError(f"Project not found: {path}")
    return path


def ensure_shot_graph(project: Path) -> dict[str, Any]:
    from lookbook.pipeline.shot_graph import build_shot_graph

    graph_path = project / "analysis" / "shot_graph.json"
    if not graph_path.exists():
        build_shot_graph(project)
    return json.loads(graph_path.read_text(encoding="utf-8"))


def build_director_packet(project: Path, target: str = "runway") -> dict[str, Any]:
    from lookbook.pipeline.director_ai import export_director_packet, generate_director_decisions

    decision = generate_director_decisions(project, target=target)
    packet_path = export_director_packet(project, target=target)
    return {
        "packet_path": str(packet_path),
        "target": target,
        "emotional_arc": decision.emotional_arc,
        "pacing_notes": decision.pacing_notes,
    }


def export_cineforge(project: Path) -> dict[str, Any]:
    from lookbook.pipeline.cineforge_export import export_cineforge_file

    result = export_cineforge_file(project)
    return {"output_path": str(result["output_path"]), "shot_count": result["shot_count"]}


def export_living_panels(project: Path) -> dict[str, Any]:
    from lookbook.pipeline.living_panels_export import export_living_panels

    out = export_living_panels(project)
    return {"output_path": str(out)}