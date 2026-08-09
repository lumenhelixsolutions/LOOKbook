"""LangGraph nodes for lookBOOK director pipeline (M17)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from lookbook_client import (
    build_director_packet,
    ensure_shot_graph,
    export_cineforge,
    export_living_panels,
    resolve_project,
)


class GraphState(TypedDict, total=False):
    project_path: str
    target: str
    dry_run_mode: bool
    auto_approve: bool
    shot_graph: dict
    director_packet: dict
    approved_export: bool
    cineforge_export: dict
    living_panels_export: dict
    review_summary: dict
    error: str | None


def node_resolve_project(state: GraphState) -> GraphState:
    try:
        project = resolve_project(state.get("project_path") or "")
        return {**state, "project_path": str(project), "error": None}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": str(exc)}


def node_shot_graph(state: GraphState) -> GraphState:
    if state.get("error"):
        return state
    try:
        project = Path(state["project_path"])
        if state.get("dry_run_mode") and (project / "analysis" / "shot_graph.json").exists():
            import json

            graph = json.loads((project / "analysis" / "shot_graph.json").read_text(encoding="utf-8"))
            return {**state, "shot_graph": graph, "error": None}
        graph = ensure_shot_graph(project)
        return {**state, "shot_graph": graph, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": str(exc)}


def node_director_packet(state: GraphState) -> GraphState:
    if state.get("error"):
        return state
    try:
        project = Path(state["project_path"])
        target = state.get("target") or "runway"
        if state.get("dry_run_mode"):
            return {
                **state,
                "director_packet": {
                    "target": target,
                    "dryRun": True,
                    "message": "director packet preview only",
                },
                "error": None,
            }
        packet = build_director_packet(project, target=target)
        return {**state, "director_packet": packet, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": str(exc)}


def node_approve_export(state: GraphState) -> GraphState:
    if state.get("error"):
        return state
    auto = state.get("auto_approve") or os.environ.get("DIRECTOR_GRAPH_AUTO_APPROVE", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if auto or state.get("dry_run_mode"):
        return {**state, "approved_export": True}
    packet = state.get("director_packet") or {}
    print(
        f"\n[approve_export] Export director packet for {packet.get('target', 'runway')}? (y/N): ",
        end="",
        flush=True,
    )
    answer = input().strip().lower()
    if answer not in ("y", "yes"):
        return {**state, "approved_export": False, "error": "export rejected"}
    return {**state, "approved_export": True}


def node_export_cineforge(state: GraphState) -> GraphState:
    if state.get("error") or not state.get("approved_export"):
        return state
    if state.get("dry_run_mode"):
        return {
            **state,
            "cineforge_export": {"dryRun": True, "message": "cineforge export skipped"},
            "error": None,
        }
    try:
        result = export_cineforge(Path(state["project_path"]))
        return {**state, "cineforge_export": result, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": str(exc)}


def node_export_living_panels(state: GraphState) -> GraphState:
    if state.get("error") or not state.get("approved_export"):
        return state
    if state.get("dry_run_mode"):
        return {
            **state,
            "living_panels_export": {"dryRun": True, "message": "living panels export skipped"},
            "error": None,
        }
    try:
        choreo = Path(state["project_path"]) / "analysis" / "choreography.json"
        if not choreo.exists():
            return {
                **state,
                "living_panels_export": {"skipped": True, "message": "no choreography.json"},
                "error": None,
            }
        result = export_living_panels(Path(state["project_path"]))
        return {**state, "living_panels_export": result, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": str(exc)}


def node_review_loop(state: GraphState) -> GraphState:
    if state.get("error"):
        return state
    shots = (state.get("shot_graph") or {}).get("shots") or []
    exports = {
        "cineforge": state.get("cineforge_export"),
        "living_panels": state.get("living_panels_export"),
    }
    return {
        **state,
        "review_summary": {
            "shot_count": len(shots),
            "exports": exports,
            "director_target": (state.get("director_packet") or {}).get("target"),
        },
        "error": None,
    }