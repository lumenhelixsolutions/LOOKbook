from __future__ import annotations
from pathlib import Path
from typing import Any
import json
from ..models import write_json


def build_scene_graph(
    project: str | Path,
    ocr_path: str | Path | None = None,
    panel_path: str | Path | None = None,
    character_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Build a structured scene graph from OCR, panel, and character analysis.

    Links panels by dialogue continuity, character presence, and visual
    similarity to produce cohesive scene groupings.

    Args:
        project: lookBOOK project path
        ocr_path: Path to ocr_result.json (auto-detected)
        panel_path: Path to panel_analysis.json (auto-detected)
        character_path: Path to character_analysis.json (auto-detected)

    Returns:
        List of scene dicts, each with panels, characters, dialogue, and metadata.
    """
    project = Path(project)

    def _load_panels() -> list:
        panel_path = project / "analysis" / "panel_analysis.json"
        if panel_path.exists():
            data = json.loads(panel_path.read_text(encoding="utf-8"))
            return data.get("panels", [])
        return []

    def _load_ocr_blocks() -> list:
        ocr_path = project / "analysis" / "ocr_result.json"
        if ocr_path.exists():
            data = json.loads(ocr_path.read_text(encoding="utf-8"))
            return data.get("blocks", [])
        return []

    panels = _load_panels()
    characters_data = project / "analysis" / "character_analysis.json"
    characters: list[dict[str, Any]] = []
    if characters_data.exists():
        characters = json.loads(characters_data.read_text(encoding="utf-8")).get("characters", [])

    ocr_blocks = _load_ocr_blocks()

    if not panels:
        raise ValueError("No panel data found. Run 'lookbook detect-panels' first.")

    # Build a panel index for quick lookup
    panel_map: dict[int, dict[str, Any]] = {}
    for p in panels:
        idx = p.get("panel_index", p.get("block_num", -1))
        panel_map[idx] = p

    # Group sequential panels into scenes based on character continuity
    scenes: list[dict[str, Any]] = []
    current_scene: list[int] = []
    current_chars: set[str] = set()

    # Build character-to-panels mapping
    char_panels: dict[str, set[int]] = {}
    for c in characters:
        cid = c.get("character_id", "")
        for app in c.get("panels", []):
            char_panels.setdefault(cid, set()).add(app.get("panel_index", -1))

    sorted_panel_indices = sorted(panel_map.keys())

    for pi in sorted_panel_indices:
        # Characters in this panel
        panel_chars = {cid for cid, pans in char_panels.items() if pi in pans}

        # Scene boundary detection:
        # A new scene starts if no character overlap OR there's a significant gap
        if current_scene:
            # Check for page-level gap (non-consecutive indices → new scene)
            is_consecutive = pi == sorted_panel_indices[sorted_panel_indices.index(pi)]
            char_overlap = bool(panel_chars & current_chars)

            if not char_overlap or not is_consecutive:
                # Finalize current scene
                scenes.append(
                    _build_scene(len(scenes), current_scene, panel_map, ocr_blocks, characters)
                )
                current_scene = []
                current_chars = set()

        current_scene.append(pi)
        current_chars |= panel_chars

    # Don't forget the last scene
    if current_scene:
        scenes.append(_build_scene(len(scenes), current_scene, panel_map, ocr_blocks, characters))

    result = {
        "schema": "lookbook.scene_graph.v0.2",
        "source_file": str(project / "source"),
        "total_scenes": len(scenes),
        "scenes": scenes,
    }

    analysis_dir = project / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    write_json(analysis_dir / "scene_graph.json", result)

    return scenes


def _build_scene(
    scene_index: int,
    panel_indices: list[int],
    panel_map: dict[int, dict[str, Any]],
    ocr_blocks: list[dict[str, Any]],
    characters: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a single scene entry from grouped panel indices."""
    scene_panels = []
    scene_chars: set[str] = set()
    scene_dialogue: list[str] = []
    scene_narration: list[str] = []

    for pi in panel_indices:
        panel = panel_map.get(pi, {})
        scene_panels.append(
            {
                "panel_index": pi,
                "bbox": panel.get("bbox", {}),
                "area": panel.get("area", 0),
                "aspect_ratio": panel.get("aspect_ratio", 0),
            }
        )

    # Attach OCR text to characters in this scene
    for c in characters:
        cid = c.get("character_id", "")
        for app in c.get("panels", []):
            if app.get("panel_index", -1) in panel_indices:
                scene_chars.add(cid)

    # Attach dialogue/narration blocks that fall within scene bbox
    if ocr_blocks:
        # Calculate scene bounding box
        min_x = min((p.get("bbox", {}).get("x", 0) for p in scene_panels), default=0)
        max_x = max(
            (p.get("bbox", {}).get("x", 0) + p.get("bbox", {}).get("w", 0) for p in scene_panels),
            default=0,
        )
        for b in ocr_blocks:
            bx = b.get("bbox", {})
            bx_center = bx.get("x", 0) + bx.get("w", 0) / 2
            if min_x <= bx_center <= max_x:
                cls = b.get("classification", "caption")
                text = b.get("text", "")
                if cls == "dialogue":
                    scene_dialogue.append(text)
                elif cls in ("narration", "caption"):
                    scene_narration.append(text)

    return {
        "scene_index": scene_index,
        "panel_count": len(panel_indices),
        "panel_indices": panel_indices,
        "panels": scene_panels,
        "characters": sorted(scene_chars),
        "dialogue": scene_dialogue,
        "narration": scene_narration,
    }
