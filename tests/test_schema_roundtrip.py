"""Schema round-trip serialization / deserialization tests.

For each major schema: create a valid instance, serialize to JSON,
deserialize back, and assert equality. Also verify that invalid JSON
raises pydantic.ValidationError.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from lookbook.schemas import (
    BBox,
    Character,
    CharacterAnalysis,
    CharacterAppearance,
    Panel,
    PanelAnalysis,
    Scene,
    SceneGraph,
    Shot,
    ShotGraph,
)


class TestSceneGraphRoundTrip:
    def test_valid_roundtrip(self):
        original = SceneGraph(
            total_scenes=2,
            scenes=[
                Scene(
                    scene_index=0,
                    panel_count=2,
                    panel_indices=[0, 1],
                    panels=[
                        Panel(
                            panel_index=0,
                            bbox=BBox(x=0, y=0, width=100, height=100),
                        ),
                        Panel(
                            panel_index=1,
                            bbox=BBox(x=100, y=0, width=100, height=100),
                        ),
                    ],
                    characters=["Hero"],
                    dialogue=["Hello"],
                    narration=["Once upon a time"],
                ),
                Scene(
                    scene_index=1,
                    panel_count=1,
                    panel_indices=[2],
                    panels=[
                        Panel(
                            panel_index=2,
                            bbox=BBox(x=0, y=100, width=200, height=100),
                        )
                    ],
                    characters=["Villain"],
                    dialogue=[],
                    narration=[],
                ),
            ],
        )
        json_str = original.model_dump_json(by_alias=True)
        restored = SceneGraph.model_validate_json(json_str)
        assert restored.total_scenes == original.total_scenes
        assert len(restored.scenes) == len(original.scenes)
        assert restored.scenes[0].scene_index == 0
        assert restored.scenes[0].characters == ["Hero"]
        assert restored.scenes[1].panel_count == 1

    def test_invalid_deserialization_raises(self):
        with pytest.raises(ValidationError):
            SceneGraph.model_validate_json(
                json.dumps({"total_scenes": "not_an_int"})
            )


class TestShotGraphRoundTrip:
    def test_valid_roundtrip(self):
        original = ShotGraph(
            total_shots=2,
            shots=[
                Shot(
                    shot_index=0,
                    type="establishing",
                    duration_seconds=4.0,
                    camera="pan right",
                    panels=[0, 1],
                    characters=["Hero"],
                ),
                Shot(
                    shot_index=1,
                    type="dialogue",
                    duration_seconds=3.5,
                    camera="static",
                    panels=[2],
                    dialogue=["Hello"],
                ),
            ],
        )
        json_str = original.model_dump_json(by_alias=True)
        restored = ShotGraph.model_validate_json(json_str)
        assert restored.total_shots == original.total_shots
        assert len(restored.shots) == len(original.shots)
        assert restored.shots[0].shot_index == 0
        assert restored.shots[0].frame_count == 96
        assert restored.shots[1].type == "dialogue"

    def test_invalid_deserialization_raises(self):
        with pytest.raises(ValidationError):
            ShotGraph.model_validate_json(
                json.dumps({"total_shots": -1})
            )


class TestCharacterAnalysisRoundTrip:
    def test_valid_roundtrip(self):
        original = CharacterAnalysis(
            total_characters=1,
            characters=[
                Character(
                    character_id="char_001",
                    name="Hero",
                    appearances=3,
                    panels=[
                        CharacterAppearance(
                            panel_index=0,
                            bbox=BBox(x=10, y=10, width=50, height=50),
                        ),
                        CharacterAppearance(
                            panel_index=1,
                            bbox=BBox(x=70, y=10, width=50, height=50),
                        ),
                    ],
                )
            ],
        )
        json_str = original.model_dump_json(by_alias=True)
        restored = CharacterAnalysis.model_validate_json(json_str)
        assert restored.total_characters == original.total_characters
        assert restored.characters[0].name == "Hero"
        assert len(restored.characters[0].panels) == 2
        assert restored.characters[0].panels[1].bbox.x == 70

    def test_invalid_deserialization_raises(self):
        with pytest.raises(ValidationError):
            CharacterAnalysis.model_validate_json(
                json.dumps({"total_characters": "many"})
            )


class TestPanelAnalysisRoundTrip:
    def test_valid_roundtrip(self):
        original = PanelAnalysis(
            total_panels=2,
            panels=[
                Panel(
                    panel_index=0,
                    bbox=BBox(x=0, y=0, width=200, height=150),
                    area=30000,
                ),
                Panel(
                    panel_index=1,
                    bbox=BBox(x=200, y=0, width=200, height=150),
                    area=30000,
                ),
            ],
            source_width=400,
            source_height=150,
        )
        json_str = original.model_dump_json(by_alias=True)
        restored = PanelAnalysis.model_validate_json(json_str)
        assert restored.total_panels == original.total_panels
        assert restored.source_width == 400
        assert restored.panels[0].panel_index == 0
        assert restored.panels[1].bbox.x == 200

    def test_invalid_deserialization_raises(self):
        with pytest.raises(ValidationError):
            PanelAnalysis.model_validate_json(
                json.dumps({"total_panels": -5})
            )
