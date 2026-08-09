from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import write_json

_WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)


def build_choreography(
    project: str | Path,
    ocr_path: str | Path | None = None,
    panel_path: str | Path | None = None,
    character_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Build speech-driven choreography lines from panels, OCR, and characters.

    Each line links dialogue/narration to a panel, bubble bbox, inferred speaker,
    and word list for browser SpeechSynthesis boundary sync.
    """
    project = Path(project)
    analysis = project / "analysis"

    if panel_path is None:
        panel_path = analysis / "panel_analysis.json"
    else:
        panel_path = Path(panel_path)

    if ocr_path is None:
        ocr_path = analysis / "ocr_result.json"
    else:
        ocr_path = Path(ocr_path)

    if character_path is None:
        character_path = analysis / "character_analysis.json"
    else:
        character_path = Path(character_path)

    if not panel_path.exists():
        raise FileNotFoundError(
            f"Panel analysis not found at {panel_path}. Run 'lookbook detect-panels' first."
        )

    panels = json.loads(panel_path.read_text(encoding="utf-8")).get("panels", [])
    if not panels:
        raise ValueError("No panels found in panel analysis.")

    panel_map: dict[int, dict[str, Any]] = {}
    for p in panels:
        idx = p.get("panel_index", p.get("block_num", -1))
        panel_map[idx] = p

    ocr_blocks: list[dict[str, Any]] = []
    if ocr_path.exists():
        ocr_data = json.loads(ocr_path.read_text(encoding="utf-8"))
        ocr_blocks = ocr_data.get("blocks", [])

    characters: list[dict[str, Any]] = []
    if character_path.exists():
        characters = json.loads(character_path.read_text(encoding="utf-8")).get("characters", [])

    lines: list[dict[str, Any]] = []
    speech_blocks = [
        b
        for b in ocr_blocks
        if b.get("classification") in ("dialogue", "narration", "caption")
        and b.get("text", "").strip()
    ]

    # Reading order: top-to-bottom, left-to-right
    speech_blocks.sort(key=lambda b: (b.get("bbox", {}).get("y", 0), b.get("bbox", {}).get("x", 0)))

    for block in speech_blocks:
        panel_index = _panel_for_bbox(block.get("bbox", {}), panel_map)
        if panel_index is None:
            continue

        text = block.get("text", "").strip()
        cls = block.get("classification", "caption")
        speaker = _speaker_for_block(block, panel_index, characters, cls)
        words = _WORD_RE.findall(text)

        lines.append(
            {
                "line_index": len(lines),
                "speaker": speaker,
                "text": text,
                "classification": cls,
                "panel_index": panel_index,
                "bubble_bbox": block.get("bbox", {}),
                "word_count": len(words),
                "words": words,
            }
        )

    voice_cast = _build_voice_cast(characters, lines)

    result = {
        "schema": "lookbook.choreography.v0.1",
        "source_file": str(project / "source"),
        "total_lines": len(lines),
        "lines": lines,
        "voice_cast": voice_cast,
    }

    analysis.mkdir(parents=True, exist_ok=True)
    write_json(analysis / "choreography.json", result)
    return lines


def camera_for_line(line: dict[str, Any] | None, panel_bbox: dict[str, Any] | None = None) -> str:
    """Derive a camera move from an active choreography line and optional panel frame."""
    if not line:
        return "static"

    cls = line.get("classification", "dialogue")
    if cls in ("narration", "caption"):
        return "crane up" if cls == "narration" else "static"

    bubble = line.get("bubble_bbox") or {}
    frame = panel_bbox or {}
    frame_w = frame.get("w", frame.get("width", 0)) or 1
    bubble_x = bubble.get("x", 0)
    bubble_w = bubble.get("w", bubble.get("width", 0))
    center = bubble_x + bubble_w / 2
    ratio = center / frame_w

    if ratio < 0.33:
        return "track right"
    if ratio > 0.66:
        return "track left"
    return "push in"


def _panel_for_bbox(bbox: dict[str, Any], panel_map: dict[int, dict[str, Any]]) -> int | None:
    cx = bbox.get("x", 0) + bbox.get("w", bbox.get("width", 0)) / 2
    cy = bbox.get("y", 0) + bbox.get("h", bbox.get("height", 0)) / 2

    best_idx: int | None = None
    best_area = float("inf")

    for idx, panel in panel_map.items():
        pb = panel.get("bbox", {})
        px, py = pb.get("x", 0), pb.get("y", 0)
        pw = pb.get("w", pb.get("width", 0))
        ph = pb.get("h", pb.get("height", 0))
        if px <= cx <= px + pw and py <= cy <= py + ph:
            area = pw * ph
            if area < best_area:
                best_area = area
                best_idx = idx

    if best_idx is not None:
        return best_idx

    # Fallback: nearest panel center
    nearest: int | None = None
    nearest_dist = float("inf")
    for idx, panel in panel_map.items():
        pb = panel.get("bbox", {})
        pcx = pb.get("x", 0) + pb.get("w", pb.get("width", 0)) / 2
        pcy = pb.get("y", 0) + pb.get("h", pb.get("height", 0)) / 2
        dist = (cx - pcx) ** 2 + (cy - pcy) ** 2
        if dist < nearest_dist:
            nearest_dist = dist
            nearest = idx
    return nearest


def _speaker_for_block(
    block: dict[str, Any],
    panel_index: int,
    characters: list[dict[str, Any]],
    classification: str,
) -> str:
    if classification in ("narration", "caption"):
        return "narrator"

    bubble = block.get("bbox", {})
    bx = bubble.get("x", 0) + bubble.get("w", bubble.get("width", 0)) / 2
    by = bubble.get("y", 0) + bubble.get("h", bubble.get("height", 0)) / 2

    best_id = "unknown"
    best_dist = float("inf")

    for char in characters:
        for app in char.get("panels", []):
            if app.get("panel_index") != panel_index:
                continue
            cb = app.get("bbox", {})
            cx = cb.get("x", 0) + cb.get("w", cb.get("width", 0)) / 2
            cy = cb.get("y", 0) + cb.get("h", cb.get("height", 0)) / 2
            dist = (bx - cx) ** 2 + (by - cy) ** 2
            if dist < best_dist:
                best_dist = dist
                best_id = char.get("name") or char.get("character_id", "unknown")

    return best_id


def _build_voice_cast(
    characters: list[dict[str, Any]],
    lines: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Map speakers to browser voice hints (pitch/rate) for SpeechSynthesis."""
    speakers = sorted({ln["speaker"] for ln in lines})
    cast: dict[str, dict[str, Any]] = {}
    voices = [
        {"pitch": 1.0, "rate": 1.0},
        {"pitch": 0.85, "rate": 0.95},
        {"pitch": 1.15, "rate": 1.05},
        {"pitch": 0.75, "rate": 0.9},
        {"pitch": 1.25, "rate": 1.1},
    ]

    char_names = {c.get("character_id", ""): c.get("name", "") for c in characters}

    for i, speaker in enumerate(speakers):
        profile = voices[i % len(voices)]
        cast[speaker] = {
            "display_name": char_names.get(speaker, speaker),
            "pitch": profile["pitch"],
            "rate": profile["rate"],
        }

    return cast


def load_choreography(project: str | Path) -> dict[str, Any] | None:
    path = Path(project) / "analysis" / "choreography.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))