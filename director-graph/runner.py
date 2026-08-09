"""LangGraph runner for lookBOOK director pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from nodes import (
    GraphState,
    node_approve_export,
    node_director_packet,
    node_export_cineforge,
    node_export_living_panels,
    node_resolve_project,
    node_review_loop,
    node_shot_graph,
)

ROOT = Path(__file__).resolve().parent


def load_graph_profiles() -> dict[str, Any]:
    path = ROOT / "graph_profiles.json"
    if not path.exists():
        return {"version": 1, "profiles": {}, "graphs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_profile_config(profile_id: str) -> dict[str, Any]:
    doc = load_graph_profiles()
    profiles = doc.get("profiles") or {}
    cfg = profiles.get(profile_id) or {}
    return {
        "profile_id": profile_id,
        "target": cfg.get("target") or "runway",
        "graph": cfg.get("graph") or "lookbook-director-pipeline",
    }


def should_continue_after_approve(state: GraphState) -> str:
    if state.get("error") or not state.get("approved_export"):
        return "end"
    return "export_cineforge"


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("resolve_project", node_resolve_project)
    graph.add_node("shot_graph", node_shot_graph)
    graph.add_node("director_packet", node_director_packet)
    graph.add_node("approve_export", node_approve_export)
    graph.add_node("export_cineforge", node_export_cineforge)
    graph.add_node("export_living_panels", node_export_living_panels)
    graph.add_node("review_loop", node_review_loop)

    graph.set_entry_point("resolve_project")
    graph.add_edge("resolve_project", "shot_graph")
    graph.add_edge("shot_graph", "director_packet")
    graph.add_edge("director_packet", "approve_export")
    graph.add_conditional_edges(
        "approve_export",
        should_continue_after_approve,
        {"export_cineforge": "export_cineforge", "end": END},
    )
    graph.add_edge("export_cineforge", "export_living_panels")
    graph.add_edge("export_living_panels", "review_loop")
    graph.add_edge("review_loop", END)
    return graph.compile()


def invoke_graph(
    profile_id: str,
    *,
    project_path: str,
    dry_run_mode: bool = False,
    auto_approve: bool = False,
    target: str | None = None,
) -> dict[str, Any]:
    cfg = resolve_profile_config(profile_id)
    initial: GraphState = {
        "project_path": project_path,
        "target": target or cfg["target"],
        "dry_run_mode": dry_run_mode,
        "auto_approve": auto_approve,
        "approved_export": False,
    }
    app = build_graph()
    final = app.invoke(initial)
    return {
        "ok": not final.get("error"),
        "profile_id": profile_id,
        "project_path": project_path,
        "config": cfg,
        "state": final,
        "error": final.get("error"),
        "dry_run_mode": dry_run_mode,
        "exported": bool((final.get("cineforge_export") or {}).get("output_path")),
    }