from __future__ import annotations
from pathlib import Path
from typing import Any
import json
from ..models import write_json
from .choreography import camera_for_line, load_choreography


def build_shot_graph(
    project: str | Path,
    scene_graph_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Generate a shot-by-shot breakdown for animation handoff.

    Converts each scene into a timed shot list with camera cues,
    motion directives, and panel transitions, ready for Runway/Veo/Kling
    integration.

    When choreography.json exists with lines, emits one shot per
    dialogue/narration line. Otherwise falls back to one shot per scene.

    Args:
        project: lookBOOK project path
        scene_graph_path: Path to scene_graph.json (auto-detected)

    Returns:
        List of shot dicts, each with timing, camera instruction, and panel refs.
    """
    project = Path(project)

    if scene_graph_path is None:
        scene_graph_path = project / "analysis" / "scene_graph.json"

    if not scene_graph_path.exists():
        raise FileNotFoundError(
            f"Scene graph not found at {scene_graph_path}. Run 'lookbook build-scene-graph' first."
        )

    scene_data = json.loads(scene_graph_path.read_text(encoding="utf-8"))
    scenes = scene_data.get("scenes", [])

    if not scenes:
        raise ValueError("No scenes found in scene graph.")

    choreography = load_choreography(project)
    choreo_lines: list[dict[str, Any]] = choreography.get("lines", []) if choreography else []

    panel_bbox_map, panel_scene_map = _build_panel_maps(scenes)

    if choreo_lines:
        shots, total_time = _build_shots_from_choreography(
            choreo_lines, scenes, panel_bbox_map, panel_scene_map
        )
    else:
        shots, total_time = _build_shots_from_scenes(scenes)

    result = {
        "schema": "lookbook.shot_graph.v0.2",
        "source_file": scene_data.get("source_file", str(project / "source")),
        "total_shots": len(shots),
        "total_duration_seconds": round(total_time, 1),
        "fps": 24,
        "frames": int(total_time * 24),
        "shots": shots,
    }

    analysis_dir = project / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    write_json(analysis_dir / "shot_graph.json", result)

    return shots


def _build_panel_maps(
    scenes: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], dict[int, int]]:
    """Map panel indices to bbox and owning scene."""
    panel_bbox_map: dict[int, dict[str, Any]] = {}
    panel_scene_map: dict[int, int] = {}

    for scene in scenes:
        scene_index = scene.get("scene_index", 0)
        for panel in scene.get("panels", []):
            panel_index = panel.get("panel_index")
            if panel_index is None:
                continue
            panel_bbox_map[panel_index] = panel.get("bbox", {})
            panel_scene_map[panel_index] = scene_index

        for panel_index in scene.get("panel_indices", []):
            panel_scene_map.setdefault(panel_index, scene_index)

    return panel_bbox_map, panel_scene_map


def _duration_for_line(line: dict[str, Any]) -> float:
    """Timing from word count (~3 words/sec, minimum 2s)."""
    word_count = line.get("word_count", 0)
    if word_count == 0 and line.get("text"):
        word_count = len(line["text"].split())
    return max(2.0, word_count / 3.0)


def _shot_type_for_line(line: dict[str, Any]) -> str:
    cls = line.get("classification", "dialogue")
    if cls == "dialogue":
        return "dialogue"
    if cls in ("narration", "caption"):
        return "action"
    return "establishing"


def _build_shots_from_choreography(
    choreo_lines: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    panel_bbox_map: dict[int, dict[str, Any]],
    panel_scene_map: dict[int, int],
) -> tuple[list[dict[str, Any]], float]:
    """One shot per choreography line (dialogue/narration)."""
    scene_by_index = {scene["scene_index"]: scene for scene in scenes}
    shots: list[dict[str, Any]] = []
    total_time = 0.0
    prev_scene_index: int | None = None

    for line in choreo_lines:
        panel_index = line.get("panel_index", -1)
        scene_index = panel_scene_map.get(panel_index, scenes[0]["scene_index"])
        scene = scene_by_index.get(scene_index, {})
        panel_bbox = panel_bbox_map.get(panel_index, {})

        shot_type = _shot_type_for_line(line)
        duration = _duration_for_line(line)
        camera = camera_for_line(line, panel_bbox)

        if prev_scene_index is None:
            transition_in = "cut"
        elif prev_scene_index == scene_index:
            transition_in = "dissolve"
        else:
            transition_in = "cut"

        text = line.get("text", "")
        cls = line.get("classification", "dialogue")
        dialogue = [text] if cls == "dialogue" else []
        narration = [text] if cls in ("narration", "caption") else []

        shot = {
            "shot_index": len(shots),
            "scene_index": scene_index,
            "type": shot_type,
            "duration_seconds": round(duration, 1),
            "start_time": round(total_time, 1),
            "end_time": round(total_time + duration, 1),
            "panels": [panel_index] if panel_index >= 0 else [],
            "panel_count": 1 if panel_index >= 0 else 0,
            "panel": panel_index,
            "camera": camera,
            "choreography_line_index": line.get("line_index"),
            "active_speaker": line.get("speaker"),
            "transition_in": transition_in,
            "dialogue": dialogue,
            "narration": narration,
            "characters": scene.get("characters", []),
            "motion_directive": _generate_motion_directive(
                shot_type, 1, cls == "dialogue"
            ),
        }

        shots.append(shot)
        total_time += duration
        prev_scene_index = scene_index

    return shots, total_time


def _build_shots_from_scenes(
    scenes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    """Fallback: one shot per scene when choreography is absent."""
    CAMERA_MOVES = [
        "pan right",
        "pan left",
        "zoom in",
        "zoom out",
        "dolly in",
        "dolly out",
        "tilt up",
        "tilt down",
        "static",
        "crane up",
        "crane down",
        "track right",
        "track left",
        "push in",
        "pull out",
    ]

    TRANSITIONS = ["cut", "fade in", "fade out", "dissolve", "wipe left", "wipe right"]

    shot_timing = {
        "establishing": 4.0,
        "dialogue": 3.5,
        "action": 2.5,
        "transition": 1.0,
    }

    shots: list[dict[str, Any]] = []
    total_time = 0.0

    for scene in scenes:
        panel_indices = scene.get("panel_indices", [])
        panel_count = scene.get("panel_count", len(panel_indices))
        dialogue = scene.get("dialogue", [])
        narration = scene.get("narration", [])

        if panel_count == 0:
            continue

        cam_idx = scene["scene_index"] % len(CAMERA_MOVES)
        camera = CAMERA_MOVES[cam_idx]
        trans_idx = (scene["scene_index"] + 1) % len(TRANSITIONS)

        has_dialogue = len(dialogue) > 0
        has_action = len(narration) > 0

        if has_dialogue:
            shot_type = "dialogue"
        elif has_action:
            shot_type = "action"
        else:
            shot_type = "establishing"

        duration = shot_timing.get(shot_type, 3.0)

        if has_dialogue:
            words = sum(len(d.split()) for d in dialogue)
            duration = max(duration, words / 3.0)

        shot = {
            "shot_index": len(shots),
            "scene_index": scene["scene_index"],
            "type": shot_type,
            "duration_seconds": round(duration, 1),
            "start_time": round(total_time, 1),
            "end_time": round(total_time + duration, 1),
            "panels": panel_indices,
            "panel_count": panel_count,
            "camera": camera,
            "choreography_line_index": None,
            "active_speaker": None,
            "transition_in": TRANSITIONS[trans_idx],
            "dialogue": dialogue,
            "narration": narration,
            "characters": scene.get("characters", []),
            "motion_directive": _generate_motion_directive(shot_type, panel_count, has_dialogue),
        }

        shots.append(shot)
        total_time += duration

        if scene["scene_index"] < len(scenes) - 1:
            trans_shot = {
                "shot_index": len(shots),
                "scene_index": scene["scene_index"],
                "type": "transition",
                "duration_seconds": shot_timing["transition"],
                "start_time": round(total_time, 1),
                "end_time": round(total_time + shot_timing["transition"], 1),
                "panels": [],
                "panel_count": 0,
                "camera": "static",
                "transition_in": "dissolve",
                "dialogue": [],
                "narration": [],
                "characters": [],
                "motion_directive": "Transition between scenes.",
            }
            shots.append(trans_shot)
            total_time += shot_timing["transition"]

    return shots, total_time


def _generate_motion_directive(shot_type: str, panel_count: int, has_dialogue: bool) -> str:
    """Generate a human-readable motion directive for the shot."""
    if shot_type == "establishing":
        return (
            f"Slow establishing view across {panel_count} panel area. "
            "Gentle pan to reveal scene layout."
        )
    elif shot_type == "dialogue":
        return (
            "Focus on character interaction. "
            "Subtle zoom during dialogue exchange. "
            "Maintain eye-line continuity between speakers."
        )
    elif shot_type == "action":
        return (
            "Dynamic camera movement. "
            "Quick cuts between action beats. "
            "Emphasize motion with whip pans on impact."
        )
    return "Static frame with gentle micro-movement."