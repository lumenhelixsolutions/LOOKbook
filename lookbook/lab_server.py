"""lookBOOK — Demo Lab Real Bridge (M4)

A lightweight HTTP API server that connects the browser demo lab
to the Python pipeline. Uses only stdlib (no FastAPI/Flask dep)
to keep the install footprint minimal.

Endpoints:
  POST /api/analyze       — run full pipeline on uploaded image
  POST /api/extract-text  — OCR on uploaded image
  POST /api/panels        — panel detection
  GET  /api/project/{id}  — read project analysis JSONs
  GET  /api/export/{id}   — list export artifacts
  POST /api/vision        — run vision LLM on uploaded image
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from threading import Thread

from .project import init_project
from .pipeline.analyze import analyze_source
from .pipeline.ocr import extract_text
from .pipeline.panels import detect_panels
from .pipeline.vision_enhanced import analyze_source_vision
from .pipeline.director_ai import generate_director_decisions


PROJECTS_ROOT = Path(tempfile.gettempdir()) / "lookbook_lab_projects"
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)


def _json_response(handler, status: int, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_multipart_image(handler) -> tuple[Path, Path]:
    """Naive multipart parser that extracts the first file upload."""
    content_type = handler.headers.get("Content-Type", "")
    if "boundary=" not in content_type:
        raise ValueError("Missing boundary")
    boundary = content_type.split("boundary=")[1].encode()
    length = int(handler.headers.get("Content-Length", 0))
    data = handler.rfile.read(length)

    parts = data.split(b"--" + boundary)
    for part in parts:
        if b'Content-Disposition: form-data; name="file"' in part or b"filename=" in part:
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            file_data = part[header_end + 4 :].rstrip(b"\r\n")
            project_id = str(uuid.uuid4())[:8]
            project_dir = PROJECTS_ROOT / project_id
            project_dir.mkdir(parents=True, exist_ok=True)
            img_path = project_dir / "source.png"
            img_path.write_bytes(file_data)
            init_project(project_dir, f"lab-{project_id}")
            return img_path, project_dir
    raise ValueError("No file found in upload")


class LabHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Suppress default logging noise
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/project/"):
            project_id = path.split("/")[-1]
            project_dir = PROJECTS_ROOT / project_id
            if not project_dir.exists():
                _json_response(self, 404, {"error": "Project not found"})
                return
            files = {}
            for json_file in (project_dir / "analysis").glob("*.json"):
                try:
                    files[json_file.stem] = json.loads(json_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            _json_response(self, 200, {"project_id": project_id, "analysis": files})
            return

        if path.startswith("/api/export/"):
            project_id = path.split("/")[-1]
            project_dir = PROJECTS_ROOT / project_id
            if not project_dir.exists():
                _json_response(self, 404, {"error": "Project not found"})
                return
            artifacts = {}
            for platform_dir in (project_dir / "exports").iterdir():
                if platform_dir.is_dir():
                    artifacts[platform_dir.name] = [f.name for f in platform_dir.iterdir()]
            _json_response(self, 200, {"project_id": project_id, "artifacts": artifacts})
            return

        _json_response(self, 404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/analyze":
                img_path, project_dir = _read_multipart_image(self)
                result = analyze_source(img_path, project_dir)
                _json_response(self, 200, {"project_id": project_dir.name, "result": result})
                return

            if path == "/api/extract-text":
                img_path, project_dir = _read_multipart_image(self)
                blocks = extract_text(img_path, project_dir)
                _json_response(self, 200, {"project_id": project_dir.name, "blocks": blocks})
                return

            if path == "/api/panels":
                img_path, project_dir = _read_multipart_image(self)
                panels = detect_panels(img_path, project_dir)
                _json_response(self, 200, {"project_id": project_dir.name, "panels": panels})
                return

            if path == "/api/vision":
                img_path, project_dir = _read_multipart_image(self)
                query = parse_qs(parsed.query)
                provider = query.get("provider", [None])[0]
                result = analyze_source_vision(img_path, project_dir, provider=provider)
                _json_response(self, 200, {"project_id": project_dir.name, "result": result})
                return

            if path == "/api/director":
                body_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(body_len)
                req = json.loads(body)
                project_id = req.get("project_id")
                target = req.get("target", "runway")
                project_dir = PROJECTS_ROOT / project_id
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                decision = generate_director_decisions(project_dir, target=target)
                _json_response(self, 200, decision.model_dump())
                return

            _json_response(self, 404, {"error": "Not found"})
        except Exception as exc:
            _json_response(self, 500, {"error": str(exc)})


def run_lab_server(port: int = 8042):
    server = HTTPServer(("", port), LabHandler)
    print(f"lookBOOK Lab Server running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down lab server.")
        server.shutdown()


def start_lab_server_thread(port: int = 8042) -> Thread:
    """Start the lab server in a background thread."""
    server = HTTPServer(("", port), LabHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"lookBOOK Lab Server running at http://localhost:{port}")
    return thread


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="lookBOOK Demo Lab server")
    parser.add_argument("--port", type=int, default=8042)
    args = parser.parse_args()
    run_lab_server(port=args.port)
