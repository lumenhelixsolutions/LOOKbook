"""Tests for lab_server security hardening: path traversal, body size, validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lookbook.lab_server import LabHandler, MAX_BODY_SIZE


class TestLabSecurity:
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

    def test_path_traversal_rejected(self, client):
        """Project IDs containing '..' should be rejected with 400."""
        status, body = client(
            "POST",
            "/api/director",
            data=json.dumps({"project_id": "../etc/passwd", "target": "runway"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        assert "error" in body
        assert "traversal" in body["error"].lower() or "invalid" in body["error"].lower()

    def test_path_traversal_backslash_rejected(self, client):
        """Project IDs containing backslash '..' should be rejected with 400."""
        status, body = client(
            "POST",
            "/api/director",
            data=json.dumps({"project_id": "..\\etc\\passwd", "target": "runway"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        assert "error" in body
        assert "traversal" in body["error"].lower() or "invalid" in body["error"].lower()

    def test_invalid_json_rejected(self, client):
        """Malformed JSON body should be rejected with 400."""
        status, body = client(
            "POST",
            "/api/director",
            data=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        assert "error" in body
        assert "json" in body["error"].lower()

    def test_missing_required_field_rejected(self, client):
        """Missing project_id in /api/director should be rejected with 400."""
        status, body = client(
            "POST",
            "/api/director",
            data=json.dumps({"target": "runway"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        assert "error" in body
        assert "project_id" in body["error"].lower() or "required" in body["error"].lower()

    def test_oversized_body_rejected(self, client, monkeypatch):
        """Request body larger than MAX_BODY_SIZE should be rejected with 413."""
        # Lower the limit so we don't have to allocate 10 MB in the test
        monkeypatch.setattr("lookbook.lab_server.MAX_BODY_SIZE", 100)
        big_body = b"x" * 101
        status, body = client(
            "POST",
            "/api/director",
            data=big_body,
            headers={"Content-Type": "application/json"},
        )
        assert status == 413
        assert "error" in body
        assert "too large" in body["error"].lower() or "413" in str(status)

    def test_missing_content_type_rejected(self, client):
        """POST /api/director without Content-Type should be rejected with 400."""
        status, body = client(
            "POST",
            "/api/director",
            data=json.dumps({"project_id": "abc", "target": "runway"}).encode(),
            headers={},
        )
        assert status == 400
        assert "error" in body
        assert "content-type" in body["error"].lower()

    def test_multipart_oversized_body_rejected(self, client, monkeypatch):
        """Multipart upload larger than MAX_BODY_SIZE should be rejected with 413."""
        monkeypatch.setattr("lookbook.lab_server.MAX_BODY_SIZE", 100)
        boundary = "----WebKitFormBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="test.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
            f"{'x' * 101}\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        status, resp_body = client(
            "POST",
            "/api/analyze",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert status == 413
        assert "error" in resp_body
        assert "too large" in resp_body["error"].lower() or "413" in str(status)

    def test_wrong_content_type_rejected(self, client):
        """POST /api/director without application/json should be rejected with 400."""
        status, body = client(
            "POST",
            "/api/director",
            data=json.dumps({"project_id": "abc", "target": "runway"}).encode(),
            headers={"Content-Type": "text/plain"},
        )
        assert status == 400
        assert "error" in body
        assert "content-type" in body["error"].lower()
