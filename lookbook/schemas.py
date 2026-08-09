"""lookBOOK — Pydantic schemas for pipeline data contracts.

Provides strict validation for panels, characters, scenes, and shots
so downstream exporters can rely on field presence and types.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class BBox(BaseModel):
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)


class Panel(BaseModel):
    panel_index: int = Field(..., ge=0)
    bbox: BBox = Field(default_factory=BBox)
    area: float = Field(default=0.0, ge=0.0)
    aspect_ratio: float = Field(default=0.0, ge=0.0)
    image_path: str | None = None
    classification: str | None = Field(default=None, max_length=100)


class TextBlock(BaseModel):
    text: str = Field(..., min_length=1)
    classification: str = Field(default="unknown", max_length=100)
    bbox: BBox = Field(default_factory=BBox)


class CharacterAppearance(BaseModel):
    panel_index: int = Field(..., ge=0)
    bbox: BBox = Field(default_factory=BBox)
    image_path: str | None = None


class Character(BaseModel):
    character_id: str = Field(..., min_length=1, max_length=200)
    name: str = Field(default="Unknown", min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    appearances: int = Field(default=0, ge=0)
    panels: list[CharacterAppearance] = Field(default_factory=list)


class Scene(BaseModel):
    scene_index: int = Field(..., ge=0)
    panel_count: int = Field(default=0, ge=0)
    panel_indices: list[int] = Field(default_factory=list)
    panels: list[Panel] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    dialogue: list[str] = Field(default_factory=list)
    narration: list[str] = Field(default_factory=list)


class Shot(BaseModel):
    shot_index: int = Field(..., ge=0)
    scene_index: int = Field(default=0, ge=0)
    type: str = Field(default="establishing", max_length=100)
    duration_seconds: float = Field(default=3.0, ge=0.0)
    start_time: float = Field(default=0.0, ge=0.0)
    end_time: float = Field(default=0.0, ge=0.0)
    panels: list[int] = Field(default_factory=list)
    panel_count: int = Field(default=0, ge=0)
    camera: str = Field(default="static", max_length=100)
    transition_in: str = Field(default="cut", max_length=100)
    dialogue: list[str] = Field(default_factory=list)
    narration: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    motion_directive: str = Field(default="", max_length=2000)
    negative_prompt: str = Field(default="", max_length=2000)
    motion_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def frame_count(self) -> int:
        return int(self.duration_seconds * 24)


class ShotGraph(BaseModel):
    schema_version: str = Field(default="lookbook.shot_graph.v0.3", alias="schema", max_length=100)
    total_shots: int = Field(default=0, ge=0)
    total_duration_seconds: float = Field(default=0.0, ge=0.0)
    fps: int = Field(default=24, ge=1)
    frames: int = Field(default=0, ge=0)
    shots: list[Shot] = Field(default_factory=list)
    vision_cost_usd: float | None = None
    vision_calls: int | None = Field(default=None, ge=0)


class ChoreographyLine(BaseModel):
    line_index: int = Field(..., ge=0)
    speaker: str = Field(default="unknown", max_length=200)
    text: str = Field(..., min_length=1)
    classification: str = Field(default="dialogue", max_length=100)
    panel_index: int = Field(..., ge=0)
    bubble_bbox: BBox = Field(default_factory=BBox)
    word_count: int = Field(default=0, ge=0)
    words: list[str] = Field(default_factory=list)


class Choreography(BaseModel):
    schema_version: str = Field(default="lookbook.choreography.v0.1", alias="schema", max_length=100)
    total_lines: int = Field(default=0, ge=0)
    lines: list[ChoreographyLine] = Field(default_factory=list)
    voice_cast: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SceneGraph(BaseModel):
    schema_version: str = Field(default="lookbook.scene_graph.v0.3", alias="schema", max_length=100)
    total_scenes: int = Field(default=0, ge=0)
    scenes: list[Scene] = Field(default_factory=list)
    vision_cost_usd: float | None = None
    vision_calls: int | None = Field(default=None, ge=0)


class CharacterAnalysis(BaseModel):
    schema_version: str = Field(default="lookbook.characters.v0.3", alias="schema", max_length=100)
    method: str = Field(default="classical", max_length=100)
    provider: str | None = Field(default=None, max_length=100)
    total_characters: int = Field(default=0, ge=0)
    characters: list[Character] = Field(default_factory=list)
    vision_cost_usd: float | None = None
    vision_calls: int | None = Field(default=None, ge=0)


class PanelAnalysis(BaseModel):
    schema_version: str = Field(default="lookbook.panels.v0.3", alias="schema", max_length=100)
    total_panels: int = Field(default=0, ge=0)
    panels: list[Panel] = Field(default_factory=list)
    source_width: int | None = Field(default=None, ge=0)
    source_height: int | None = Field(default=None, ge=0)


class DirectorDecision(BaseModel):
    """Director AI output — high-level creative decisions per scene or shot."""

    target: str = Field(..., min_length=1, max_length=100)  # e.g. "runway", "veo", "kling"
    pacing_notes: str = Field(default="", max_length=5000)
    emotional_arc: str = Field(default="", max_length=5000)
    camera_language: str = Field(default="", max_length=5000)
    style_presets: list[str] = Field(default_factory=list)
    quality_threshold: str = Field(default="high", max_length=100)
    negative_prompt_override: str = Field(default="", max_length=5000)


# ---------------------------------------------------------------------------
# Lab-server request schemas
# ---------------------------------------------------------------------------

class DirectorRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=200)
    target: str = Field(default="runway", max_length=100)


class AnimaticRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=200)
    shot_graph: dict[str, Any] | None = None
    clip_duration: float = Field(default=3.0, ge=0.1, le=60.0)
