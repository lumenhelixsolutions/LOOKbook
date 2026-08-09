"""Tests for Demo Lab Real Bridge HTTP server (M4)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lookbook.lab_server import LabHandler, PROJECTS_ROOT
from lookbook.project import init_project


class TestLabServer:
    @pytest.fixture
    def client(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        from http.server import HTTPServer
        import threading
        import urllib.request

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"

        def request(method, path, data=None, headers=None):
            url = base + path
            req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
            try:
                resp = urllib.request.urlopen(req, timeout=5)
                body = resp.read().decode("utf-8")
                if not body:
                    return resp.status, {}
                return resp.status, json.loads(body)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
                try:
                    return e.code, json.loads(body)
                except Exception:
                    return e.code, {"raw": body}

        yield request
        server.shutdown()

    def test_api_project_not_found(self, client):
        status, body = client("GET", "/api/project/does_not_exist")
        assert status == 404
        assert "error" in body

    def test_api_export_not_found(self, client):
        status, body = client("GET", "/api/export/does_not_exist")
        assert status == 404

    def test_serve_demo_lab_index(self, tmp_path: Path, monkeypatch):
        import threading
        import urllib.request
        from http.server import HTTPServer

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        resp = urllib.request.urlopen(f"http://{host}:{port}/", timeout=5)
        html = resp.read().decode("utf-8")
        server.shutdown()
        assert resp.status == 200
        assert "Demo Lab" in html

    def test_health_reports_capabilities(self, client):
        status, body = client("GET", "/health")
        assert status == 200
        assert body.get("version", 0) >= 5
        assert "capabilities" in body
        assert "ready_for_pipeline" in body["capabilities"]

    def test_pipeline_run_multi_panel(self, tmp_path: Path, monkeypatch):
        import io
        import threading
        import urllib.request
        from http.server import HTTPServer
        from pathlib import Path as P

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        fixture = P(__file__).resolve().parent / "fixtures" / "comic_2x2.png"
        if not fixture.exists():
            pytest.skip("comic_2x2.png missing — run scripts/generate_comic_fixture.py")

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        png_bytes = fixture.read_bytes()
        boundary = "----MultiPanelBoundary"
        body_bytes = b"".join([
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="comic_2x2.png"\r\n',
            b"Content-Type: image/png\r\n\r\n",
            png_bytes,
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        req = urllib.request.Request(
            f"http://{host}:{port}/api/pipeline/run",
            data=body_bytes,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=45)
        result = json.loads(resp.read().decode())
        server.shutdown()
        project_dir = tmp_path / "lab_projects" / result["project_id"]
        assert result["pipeline"]["panel_count"] >= 4
        assert len(result["pipeline"]["interpretation"]["scenes"]) >= 1
        ocr = json.loads((project_dir / "analysis" / "ocr_result.json").read_text(encoding="utf-8"))
        assert len(ocr.get("blocks", [])) >= 1
        assert not ocr.get("synthesized")

    def test_pipeline_run(self, client, tmp_path: Path, monkeypatch):
        from PIL import Image, ImageDraw

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        img = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 290], outline="black", width=4)
        draw.rectangle([210, 10, 390, 290], outline="black", width=4)
        draw.text((30, 40), "Hello!", fill="black")
        png_bytes = b""
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        import threading
        import urllib.request
        from http.server import HTTPServer

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address

        boundary = "----TestBoundary"
        body_bytes = b"".join([
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="source.png"\r\n',
            b"Content-Type: image/png\r\n\r\n",
            png_bytes,
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        req = urllib.request.Request(
            f"http://{host}:{port}/api/pipeline/run",
            data=body_bytes,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        server.shutdown()
        project_dir = tmp_path / "lab_projects" / result["project_id"]
        assert result["pipeline"]["panel_count"] >= 1
        assert (project_dir / "analysis" / "scene_graph.json").exists()

    def test_interpret_page(self, client, tmp_path: Path, monkeypatch):
        from PIL import Image, ImageDraw

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        project_id = "interp01"
        project_dir = tmp_path / "lab_projects" / project_id
        project_dir.mkdir(parents=True)
        init_project(project_dir, "test")
        img = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 290], outline="black", width=4)
        draw.rectangle([210, 10, 390, 290], outline="black", width=4)
        img.save(project_dir / "source.png")

        from lookbook.lab_server import _synthesize_ocr_from_panels
        from lookbook.pipeline.panels import detect_panels

        detect_panels(project_dir / "source.png", project_dir)
        _synthesize_ocr_from_panels(project_dir)

        status, body = client(
            "POST",
            "/api/interpret",
            data=json.dumps({"project_id": project_id, "use_vision": False}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        interp = body["interpretation"]
        assert interp["characters"]
        assert interp["scenes"]
        assert interp["method"] == "classical"
        assert "Vision disabled" in interp.get("vision_skipped", "")
        assert (project_dir / "analysis" / "scene_graph.json").exists()
        page_interp = json.loads(
            (project_dir / "analysis" / "page_interpretation.json").read_text(encoding="utf-8")
        )
        assert page_interp.get("vision_skipped")
        assert page_interp.get("vision_error") is None

    def _prepare_interpret_project(self, tmp_path: Path, monkeypatch, project_id: str = "vis01") -> Path:
        from PIL import Image, ImageDraw

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        project_dir = tmp_path / "lab_projects" / project_id
        project_dir.mkdir(parents=True)
        init_project(project_dir, "test")
        img = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 290], outline="black", width=4)
        draw.rectangle([210, 10, 390, 290], outline="black", width=4)
        img.save(project_dir / "source.png")

        from lookbook.lab_server import _synthesize_ocr_from_panels
        from lookbook.pipeline.panels import detect_panels

        detect_panels(project_dir / "source.png", project_dir)
        _synthesize_ocr_from_panels(project_dir)
        return project_dir

    def test_interpret_vision_skipped_without_api_key(self, client, tmp_path: Path, monkeypatch):
        project_id = "vis_skip"
        self._prepare_interpret_project(tmp_path, monkeypatch, project_id)

        with patch("lookbook.lab_server.get_api_key", return_value=""):
            status, body = client(
                "POST",
                "/api/interpret",
                data=json.dumps({"project_id": project_id, "use_vision": True}).encode(),
                headers={"Content-Type": "application/json"},
            )

        assert status == 200
        interp = body["interpretation"]
        assert interp["method"] == "classical"
        assert "no api key" in interp.get("vision_skipped", "").lower()
        assert "vision_error" not in interp

    @patch("lookbook.lab_server.build_scene_graph_vision")
    @patch("lookbook.lab_server.extract_characters_vision", return_value=[])
    @patch(
        "lookbook.lab_server.analyze_source_vision",
        return_value={"description": "LLM semantic page read for QA"},
    )
    def test_interpret_vision_success(
        self,
        _mock_analyze,
        _mock_chars,
        _mock_scenes,
        client,
        tmp_path: Path,
        monkeypatch,
    ):
        project_id = "vis_ok"
        project_dir = self._prepare_interpret_project(tmp_path, monkeypatch, project_id)

        with patch("lookbook.lab_server.get_api_key", return_value="test-key"):
            status, body = client(
                "POST",
                "/api/interpret",
                data=json.dumps({"project_id": project_id, "use_vision": True}).encode(),
                headers={"Content-Type": "application/json"},
            )

        assert status == 200
        interp = body["interpretation"]
        assert interp["method"] == "vision"
        assert interp["page_description"] == "LLM semantic page read for QA"
        assert interp.get("vision_error") is None
        page_interp = json.loads(
            (project_dir / "analysis" / "page_interpretation.json").read_text(encoding="utf-8")
        )
        assert page_interp["method"] == "vision"
        assert page_interp["page_description"] == "LLM semantic page read for QA"

    @patch(
        "lookbook.lab_server.analyze_source_vision",
        side_effect=RuntimeError("vision provider timeout"),
    )
    def test_interpret_vision_error_surfaces(
        self,
        _mock_analyze,
        client,
        tmp_path: Path,
        monkeypatch,
    ):
        project_id = "vis_err"
        self._prepare_interpret_project(tmp_path, monkeypatch, project_id)

        with patch("lookbook.lab_server.get_api_key", return_value="test-key"):
            status, body = client(
                "POST",
                "/api/interpret",
                data=json.dumps({"project_id": project_id, "use_vision": True}).encode(),
                headers={"Content-Type": "application/json"},
            )

        assert status == 200
        interp = body["interpretation"]
        assert interp["method"] == "classical"
        assert "vision provider timeout" in interp.get("vision_error", "")

    def test_pipeline_run_reuses_project_source(self, tmp_path: Path, monkeypatch):
        import threading
        import urllib.parse
        import urllib.request
        from http.server import HTTPServer
        from PIL import Image, ImageDraw

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        project_id = "reuse01"
        project_dir = tmp_path / "lab_projects" / project_id
        project_dir.mkdir(parents=True)
        init_project(project_dir, "reuse")
        img = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 290], outline="black", width=4)
        draw.rectangle([210, 10, 390, 290], outline="black", width=4)
        img.save(project_dir / "source.png")

        from lookbook.pipeline.vault_import import import_vault_manifest

        import_vault_manifest(
            project_dir,
            {
                "format": "lookbook.source_manifest.v1",
                "title": "Reuse test",
                "files": [{"name": "notes.md", "kind": "md", "content": "# Notes\n"}],
            },
        )

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        qs = urllib.parse.urlencode({"project_id": project_id})
        req = urllib.request.Request(
            f"http://{host}:{port}/api/pipeline/run?{qs}",
            data=b"",
            headers={"Content-Length": "0"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=45)
        result = json.loads(resp.read().decode())
        server.shutdown()

        assert result["project_id"] == project_id
        assert result["pipeline"]["panel_count"] >= 1
        assert (project_dir / "analysis" / "vault_import.json").exists()
        assert (project_dir / "analysis" / "panel_analysis.json").exists()

    def test_director_graph_run_endpoint(self, client, tmp_path: Path, monkeypatch):
        from unittest.mock import patch

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        project_id = "dg01"
        project_dir = tmp_path / "lab_projects" / project_id
        project_dir.mkdir(parents=True)
        init_project(project_dir, "dg")
        (project_dir / "analysis").mkdir(exist_ok=True)
        (project_dir / "analysis" / "shot_graph.json").write_text(
            json.dumps({"schema": "lookbook.shot_graph.v0.3", "shots": [{"shot_index": 0, "type": "wide", "panels": [0]}]}),
            encoding="utf-8",
        )

        mock_result = {
            "ok": True,
            "state": {"review_summary": {"shot_count": 1, "director_target": "runway"}},
        }
        with patch("lookbook.lab_server.probe_director_graph", return_value={"online": True}):
            with patch("lookbook.lab_server.run_director_graph", return_value=mock_result):
                status, body = client(
                    "POST",
                    "/api/director-graph/run",
                    data=json.dumps({"project_id": project_id}).encode(),
                    headers={"Content-Type": "application/json"},
                )
        assert status == 200
        assert body["ok"] is True
        assert body["review_summary"]["shot_count"] == 1
        record = json.loads(
            (project_dir / "analysis" / "director_graph_run.json").read_text(encoding="utf-8")
        )
        assert record["ok"] is True

    def test_import_vault_http(self, client, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        manifest = {
            "format": "lookbook.source_manifest.v1",
            "title": "HTTP Vault Import",
            "source_type": "research",
            "files": [{
                "name": "research-brief.md",
                "kind": "md",
                "content": "# Brief\nVault HTTP smoke for demo-lab import.\n",
            }],
            "metadata": {"artifactId": "http-1", "provider": "notetoolslm"},
        }
        status, body = client(
            "POST",
            "/api/import-vault",
            data=json.dumps({"manifest": manifest}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        project_id = body["project_id"]
        assert body["import"]["files_written"] == 1
        project_dir = tmp_path / "lab_projects" / project_id
        assert (project_dir / "source" / "research-brief.md").exists()
        assert (project_dir / "analysis" / "vault_import.json").exists()

    def test_serve_project_file_and_rewritten_panel_urls(self, tmp_path: Path, monkeypatch):
        import threading
        import urllib.request
        from http.server import HTTPServer
        from PIL import Image, ImageDraw

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        project_id = "fileurl1"
        project_dir = tmp_path / "lab_projects" / project_id
        project_dir.mkdir(parents=True)
        init_project(project_dir, "test")
        img = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 290], outline="black", width=4)
        draw.rectangle([210, 10, 390, 290], outline="black", width=4)
        img.save(project_dir / "source.png")

        from lookbook.pipeline.panels import detect_panels

        detect_panels(project_dir / "source.png", project_dir)

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"

        review = urllib.request.urlopen(
            f"{base}/api/living-panels/{project_id}", timeout=15
        )
        html = review.read().decode("utf-8")
        assert f"/api/project/{project_id}/file/analysis/panels/panel_000.png" in html

        panel = urllib.request.urlopen(
            f"{base}/api/project/{project_id}/file/analysis/panels/panel_000.png",
            timeout=5,
        )
        assert panel.status == 200
        assert panel.headers["Content-Type"] == "image/png"
        assert len(panel.read()) > 0
        server.shutdown()

    def test_get_living_panels_auto_build(self, tmp_path: Path, monkeypatch):
        import threading
        import urllib.request
        from http.server import HTTPServer
        from PIL import Image, ImageDraw

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        project_id = "lpauto01"
        project_dir = tmp_path / "lab_projects" / project_id
        project_dir.mkdir(parents=True)
        init_project(project_dir, "test")
        img = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 290], outline="black", width=4)
        draw.rectangle([210, 10, 390, 290], outline="black", width=4)
        img.save(project_dir / "source.png")

        from lookbook.pipeline.panels import detect_panels

        detect_panels(project_dir / "source.png", project_dir)

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        resp = urllib.request.urlopen(
            f"http://{host}:{port}/api/living-panels/{project_id}", timeout=15
        )
        html = resp.read().decode("utf-8")
        server.shutdown()
        assert resp.status == 200
        assert "Living Panels" in html
        assert (project_dir / "analysis" / "choreography.json").exists()

    def test_build_living_panels(self, client, tmp_path: Path, monkeypatch):
        import threading
        import urllib.request
        from http.server import HTTPServer
        from PIL import Image, ImageDraw

        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        project_id = "abc12345"
        project_dir = tmp_path / "lab_projects" / project_id
        project_dir.mkdir(parents=True)
        init_project(project_dir, "test")
        img = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 290], outline="black", width=4)
        draw.rectangle([210, 10, 390, 290], outline="black", width=4)
        img.save(project_dir / "source.png")

        from lookbook.pipeline.panels import detect_panels

        detect_panels(project_dir / "source.png", project_dir)

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        payload = json.dumps({"project_id": project_id}).encode()
        req = urllib.request.Request(
            f"http://{host}:{port}/api/build-living-panels",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode())
        server.shutdown()
        assert body["choreography_lines"] >= 1
        assert (project_dir / "analysis" / "choreography.json").exists()

    def test_export_cineforge_file_only(self, client, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "lookbook.lab_server.PROJECTS_ROOT", tmp_path / "lab_projects"
        )
        project_id = "cfexport"
        project_dir = tmp_path / "lab_projects" / project_id
        project_dir.mkdir(parents=True)
        init_project(project_dir, "test")
        analysis = project_dir / "analysis"
        analysis.mkdir(parents=True, exist_ok=True)
        shot_graph = {
            "schema": "lookbook.shot_graph.v0.3",
            "shots": [
                {
                    "shot_index": 0,
                    "scene_index": 0,
                    "type": "establishing",
                    "duration_seconds": 2.0,
                    "panels": [0],
                }
            ],
        }
        (analysis / "shot_graph.json").write_text(json.dumps(shot_graph), encoding="utf-8")
        payload = json.dumps({"project_id": project_id, "push": False}).encode()
        status, body = client(
            "POST",
            "/api/export-cineforge",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        assert body["shot_count"] == 1
        assert body["pushed"] is False
        assert (project_dir / "exports" / "cineforge" / "ingest.json").exists()

    def test_options_cors(self, client):
        status, _ = client("OPTIONS", "/api/analyze")
        assert status == 204

    def test_post_analyze_no_file(self, client):
        status, body = client("POST", "/api/analyze", data=b"")
        assert status == 400
        assert "error" in body

    def test_api_director_missing_project(self, client):
        status, body = client(
            "POST",
            "/api/director",
            data=json.dumps({"project_id": "missing", "target": "runway"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 404
