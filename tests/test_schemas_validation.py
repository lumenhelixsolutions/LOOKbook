"""Tests for lookBOOK Pydantic schema field validation (M5)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lookbook.schemas import BBox, Panel, Character, Shot, ShotGraph


class TestBBoxValidation:
    def test_negative_x_rejected(self):
        with pytest.raises(ValidationError):
            BBox(x=-1, y=0, width=10, height=10)

    def test_negative_y_rejected(self):
        with pytest.raises(ValidationError):
            BBox(x=0, y=-1, width=10, height=10)

    def test_negative_width_rejected(self):
        with pytest.raises(ValidationError):
            BBox(x=0, y=0, width=-1, height=10)

    def test_negative_height_rejected(self):
        with pytest.raises(ValidationError):
            BBox(x=0, y=0, width=10, height=-1)


class TestPanelValidation:
    def test_classification_max_length_enforced(self):
        with pytest.raises(ValidationError):
            Panel(panel_index=0, classification="x" * 101)

    def test_classification_within_max_length(self):
        p = Panel(panel_index=0, classification="x" * 100)
        assert p.classification == "x" * 100


class TestCharacterValidation:
    def test_name_max_length_enforced(self):
        with pytest.raises(ValidationError):
            Character(character_id="c", name="x" * 201)

    def test_name_within_max_length(self):
        c = Character(character_id="c", name="x" * 200)
        assert c.name == "x" * 200


class TestShotValidation:
    def test_negative_duration_rejected(self):
        with pytest.raises(ValidationError):
            Shot(shot_index=0, duration_seconds=-1.0)

    def test_zero_duration_allowed(self):
        s = Shot(shot_index=0, duration_seconds=0.0)
        assert s.duration_seconds == 0.0


class TestShotGraphValidation:
    def test_fps_less_than_one_rejected(self):
        with pytest.raises(ValidationError):
            ShotGraph(fps=0)

    def test_fps_one_allowed(self):
        sg = ShotGraph(fps=1)
        assert sg.fps == 1
