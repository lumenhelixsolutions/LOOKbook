"""End-to-end lab server workflow test.

Starts the lookBOOK lab server in a background thread and exercises the
full HTTP workflow: upload → analysis → export listing → animatic generation → download.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw

from lookbook.lab_server import LabHandler
from lookbook.video.animatic import _MOVIEPY, _resolve_font


def _create_comic_image(path: Path) -> Path:
    """Generate a simple comic page with bordered panels."""
    img = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 380, 280], outline="black", width=8)
    draw.rectangle([420, 20, 780, 280], outline="black", width=8)
    draw.rectangle([20, 320, 780, 580], outline="black", width=8)
    img.save(path)
    return path


def _build_multipart_image_body(image_path: Path, boundary: str = "----LabBoundary") -> bytes:
    """Build a minimal multipart/form-data body with a single file upload."""
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{image_path.name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode()
    body += image_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    return body


class TestE2ELabServer:
    @pytest.fixture
    def client(self, tmp_path: Path, monkeypatch):
        """Yield a request helper for an ephemeral lab server instance."""
        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
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
                resp = urllib.request.urlopen(req, timeout=30)
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return resp.status, json.loads(body.decode("utf-8"))
                return resp.status, body
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
                try:
                    return e.code, json.loads(body)
                except Exception:
                    return e.code, {"raw": body}

        yield request
        server.shutdown()

    @patch("lookbook.pipeline.vision_llm.get_analyzer")
    def test_full_http_workflow(self, mock_get_analyzer, client, tmp_path: Path):
        """Upload an image, read analysis, list exports, generate animatic, and download MP4."""
        image = tmp_path / "comic.png"
        _create_comic_image(image)

        # 1. POST /api/analyze — multipart upload creates project & runs analysis
        body = _build_multipart_image_body(image)
        status, data = client(
            "POST",
            "/api/analyze",
            data=body,
            headers={"Content-Type": "multipart/form-data; boundary=----LabBoundary"},
        )
        assert status == 200
        project_id = data["project_id"]
        assert data["result"]["source_file"] == "source.png"

        # 2. GET /api/project/{id} — verify analysis JSON returned
        status, data = client("GET", f"/api/project/{project_id}")
        assert status == 200
        assert data["project_id"] == project_id
        assert "analysis" in data
        assert "source_analysis" in data["analysis"]

        # 3. GET /api/export/{id} — verify export artifacts listing
        status, data = client("GET", f"/api/export/{project_id}")
        assert status == 200
        assert data["project_id"] == project_id
        assert "artifacts" in data

        # 4. POST /api/animatic with shot graph — verify animatic generated
        if not _MOVIEPY or _resolve_font() is None:
            pytest.skip("moviepy or system font required for animatic generation")

        shot_graph = {
            "schema": "lookbook.shot_graph.v0.3",
            "total_shots": 2,
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
                    "dialogue": ["Hello"],
                    "narration": [],
                    "characters": ["char_001"],
                },
            ],
        }
        payload = json.dumps({"shot_graph": shot_graph}).encode("utf-8")
        status, data = client(
            "POST",
            "/api/animatic",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        animatic_project_id = data["project_id"]
        assert data["total_shots"] == 2
        assert "preview_url" in data

        # 5. GET /api/animatic/{id} — verify MP4 downloadable
        status, body = client("GET", f"/api/animatic/{animatic_project_id}")
        assert status == 200
        assert isinstance(body, bytes)
        assert len(body) > 0

        mock_get_analyzer.assert_not_called()
