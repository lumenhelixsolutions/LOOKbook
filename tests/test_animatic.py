"""Tests for lookBOOK Shot-to-Animatic Generator (M5)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from lookbook.video.animatic import (
    _resolve_font,
    build_animatic,
    generate_shot_clip,
    shot_to_mpt_prompt,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_shot() -> dict:
    return {
        "shot_index": 7,
        "type": "dialogue",
        "camera": "zoom in",
        "motion_directive": "Focus on character interaction.",
        "dialogue": ['"Hello, this is a test."'],
        "narration": [],
        "characters": ["char_000"],
    }


@pytest.fixture
def sample_shot_graph(tmp_path: Path) -> Path:
    data = {
        "schema": "lookbook.shot_graph.v0.3",
        "total_shots": 2,
        "shots": [
            {
                "shot_index": 0,
                "type": "establishing",
                "camera": "pan right",
                "motion_directive": "Slow pan across the scene.",
                "dialogue": [],
                "narration": ["The scene opens on a vast landscape."],
                "characters": [],
            },
            {
                "shot_index": 1,
                "type": "dialogue",
                "camera": "zoom in",
                "motion_directive": "Focus on character interaction.",
                "dialogue": ['"Hello, this is a test."'],
                "narration": [],
                "characters": ["char_000"],
            },
        ],
    }
    path = tmp_path / "shot_graph.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestShotToMptPrompt:
    def test_basic_conversion(self, sample_shot: dict):
        prompt = shot_to_mpt_prompt(sample_shot)
        assert "Dialogue shot" in prompt
        assert "Camera: zoom in" in prompt
        assert "char_000" in prompt
        assert "Hello, this is a test" in prompt
        assert "Focus on character interaction" in prompt

    def test_empty_shot(self):
        shot = {"shot_index": 0, "type": "establishing", "camera": "static"}
        prompt = shot_to_mpt_prompt(shot)
        assert "Establishing shot" in prompt
        # "static" is omitted from the prompt to keep it concise
        assert "Camera: static" not in prompt


class TestResolveFont:
    def test_returns_string_or_none(self):
        font = _resolve_font()
        assert font is None or isinstance(font, str)


class TestGenerateShotClip:
    def test_generates_mp4(self, tmp_path: Path, sample_shot: dict):
        font = _resolve_font()
        if font is None:
            pytest.skip("No usable system font found")

        out = tmp_path / "shot_007.mp4"
        result = generate_shot_clip(
            sample_shot,
            out,
            duration=1.0,
            width=320,
            height=180,
            fps=12,
            font_path=font,
        )
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0

    def test_missing_font_raises(self, tmp_path: Path, sample_shot: dict):
        out = tmp_path / "shot.mp4"
        with pytest.raises(RuntimeError, match="font"):
            generate_shot_clip(
                sample_shot,
                out,
                duration=1.0,
                width=320,
                height=180,
                font_path="/nonexistent/font.ttf",
            )


class TestBuildAnimatic:
    def test_builds_concatenated_mp4(self, tmp_path: Path, sample_shot_graph: Path):
        font = _resolve_font()
        if font is None:
            pytest.skip("No usable system font found")

        output = tmp_path / "animatic.mp4"
        result = build_animatic(
            sample_shot_graph,
            output,
            clip_duration=1.0,
            width=320,
            height=180,
            fps=12,
            font_path=font,
        )
        assert output.exists()
        assert output.stat().st_size > 0
        assert result["total_shots"] == 2
        assert result["total_duration_seconds"] == 2.0
        assert result["fps"] == 12
        assert result["width"] == 320
        assert result["height"] == 180
        assert len(result["clips"]) == 2
        assert result["clips"][0]["shot_index"] == 0
        assert result["clips"][1]["shot_index"] == 1

    def test_invalid_schema_raises(self, tmp_path: Path):
        bad = {"schema": "lookbook.scene_graph.v0.3", "shots": []}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match="schema"):
            build_animatic(path, tmp_path / "out.mp4")

    def test_empty_shots_raises(self, tmp_path: Path):
        empty = {"schema": "lookbook.shot_graph.v0.3", "shots": []}
        path = tmp_path / "empty.json"
        path.write_text(json.dumps(empty), encoding="utf-8")
        with pytest.raises(ValueError, match="No shots"):
            build_animatic(path, tmp_path / "out.mp4")

    def test_keep_clips(self, tmp_path: Path, sample_shot_graph: Path):
        font = _resolve_font()
        if font is None:
            pytest.skip("No usable system font found")

        output = tmp_path / "animatic.mp4"
        result = build_animatic(
            sample_shot_graph,
            output,
            clip_duration=1.0,
            width=320,
            height=180,
            fps=12,
            font_path=font,
            keep_clips=True,
            temp_dir=tmp_path / "clips",
        )
        assert (tmp_path / "clips" / "shot_000.mp4").exists()
        assert (tmp_path / "clips" / "shot_001.mp4").exists()


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    def test_generate_animatic_cli(self, tmp_path: Path, sample_shot_graph: Path):
        from lookbook.cli import main

        output = tmp_path / "cli_animatic.mp4"
        main(
            [
                "generate-animatic",
                str(sample_shot_graph),
                "--output",
                str(output),
                "--duration",
                "1.0",
                "--width",
                "320",
                "--height",
                "180",
                "--fps",
                "12",
            ]
        )
        assert output.exists()
        assert output.stat().st_size > 0


# ---------------------------------------------------------------------------
# Web UI / Lab server tests
# ---------------------------------------------------------------------------


class TestLabServerAnimatic:
    @pytest.fixture
    def client(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        from http.server import HTTPServer
        import threading
        import urllib.request

        from lookbook.lab_server import LabHandler

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"

        def request(method, path, data=None, headers=None):
            url = base + path
            req = urllib.request.Request(
                url, data=data, headers=headers or {}, method=method
            )
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return resp.status, json.loads(body.decode("utf-8"))
                # Binary / video response
                return resp.status, body
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
                try:
                    return e.code, json.loads(body)
                except Exception:
                    return e.code, {"raw": body}

        yield request
        server.shutdown()

    def test_post_animatic_json_body(self, client):
        shot_graph = {
            "schema": "lookbook.shot_graph.v0.3",
            "total_shots": 1,
            "shots": [
                {
                    "shot_index": 0,
                    "type": "establishing",
                    "camera": "static",
                    "dialogue": [],
                    "narration": [],
                    "characters": [],
                }
            ],
        }
        payload = json.dumps({"shot_graph": shot_graph}).encode("utf-8")
        status, body = client(
            "POST",
            "/api/animatic",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        assert "project_id" in body
        assert "preview_url" in body
        assert body["total_shots"] == 1

    def test_post_animatic_missing_body(self, client):
        payload = json.dumps({}).encode("utf-8")
        status, body = client(
            "POST",
            "/api/animatic",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        assert "error" in body

    def test_get_animatic_preview(self, client):
        # First generate an animatic
        shot_graph = {
            "schema": "lookbook.shot_graph.v0.3",
            "total_shots": 1,
            "shots": [
                {
                    "shot_index": 0,
                    "type": "establishing",
                    "camera": "static",
                    "dialogue": [],
                    "narration": [],
                    "characters": [],
                }
            ],
        }
        payload = json.dumps({"shot_graph": shot_graph}).encode("utf-8")
        status, body = client(
            "POST",
            "/api/animatic",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        assert isinstance(body, dict)
        project_id = body["project_id"]

        # Now fetch the MP4
        status, resp_body = client("GET", f"/api/animatic/{project_id}")
        assert status == 200
        assert isinstance(resp_body, bytes)
        assert len(resp_body) > 0

    def test_get_animatic_not_found(self, client):
        status, body = client("GET", "/api/animatic/does_not_exist")
        assert status == 404
        assert "error" in body
