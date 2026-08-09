"""Performance smoke tests.

Ensures core operations complete within acceptable wall-clock time.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lookbook.schemas import Shot, ShotGraph
from lookbook.video.animatic import _MOVIEPY, _resolve_font, build_animatic


class TestPerformance:
    @pytest.mark.skipif(
        not _MOVIEPY or _resolve_font() is None,
        reason="moviepy or system font required for animatic generation",
    )
    def test_build_animatic_under_30s(self, tmp_path: Path):
        """build_animatic with 3 simple shots should complete in < 30 seconds."""
        shot_graph = {
            "schema": "lookbook.shot_graph.v0.3",
            "total_shots": 3,
            "shots": [
                {
                    "shot_index": 0,
                    "type": "establishing",
                    "camera": "static",
                    "dialogue": [],
                    "narration": [],
                    "characters": [],
                },
                {
                    "shot_index": 1,
                    "type": "dialogue",
                    "camera": "zoom in",
                    "dialogue": ["Hello world"],
                    "narration": [],
                    "characters": ["char_001"],
                },
                {
                    "shot_index": 2,
                    "type": "action",
                    "camera": "pan right",
                    "dialogue": [],
                    "narration": ["The chase begins"],
                    "characters": ["char_001", "char_002"],
                },
            ],
        }
        path = tmp_path / "shot_graph.json"
        path.write_text(json.dumps(shot_graph), encoding="utf-8")
        output = tmp_path / "perf_animatic.mp4"

        start = time.perf_counter()
        build_animatic(
            path,
            output,
            clip_duration=1.0,
            width=320,
            height=180,
            fps=12,
        )
        elapsed = time.perf_counter() - start

        assert output.exists()
        assert output.stat().st_size > 0
        assert elapsed < 30.0, f"build_animatic took {elapsed:.1f}s, expected < 30s"

    def test_schema_validation_1000_shots_under_1s(self):
        """Validating a 1000-shot graph should complete in < 1 second."""
        shots = [
            Shot(
                shot_index=i,
                type="establishing",
                camera="static",
                duration_seconds=3.0,
            )
            for i in range(1000)
        ]
        start = time.perf_counter()
        sg = ShotGraph(total_shots=1000, shots=shots)
        elapsed = time.perf_counter() - start

        assert sg.total_shots == 1000
        assert len(sg.shots) == 1000
        assert elapsed < 1.0, (
            f"Schema validation took {elapsed:.3f}s, expected < 1s"
        )
