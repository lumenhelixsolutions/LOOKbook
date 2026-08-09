"""HTTP smokes for director-graph sidecar (S7)."""

from __future__ import annotations

import json
import sys
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

DIRECTOR_GRAPH = Path(__file__).resolve().parents[1] / "director-graph"
sys.path.insert(0, str(DIRECTOR_GRAPH))

from server import DirectorGraphHandler  # noqa: E402


@pytest.fixture
def dg_client(tmp_path: Path):
    project = tmp_path / "dg_http"
    (project / "analysis").mkdir(parents=True)
    (project / "analysis" / "shot_graph.json").write_text(
        json.dumps({
            "schema": "lookbook.shot_graph.v0.3",
            "shots": [{
                "shot_index": 0,
                "scene_index": 0,
                "type": "establishing",
                "duration_seconds": 3.0,
                "camera": "static",
                "characters": ["Hero"],
                "motion_directive": "Hero stands.",
                "panels": [0],
            }],
        }),
        encoding="utf-8",
    )

    server = HTTPServer(("127.0.0.1", 0), DirectorGraphHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base = f"http://{host}:{port}"

    def request(method: str, path: str, data: bytes | None = None):
        req = urllib.request.Request(
            base + path,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method=method,
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read().decode())

    yield request, project
    server.shutdown()


def test_health_ok(dg_client):
    request, _ = dg_client
    status, body = request("GET", "/health")
    assert status == 200
    assert body["status"] == "ok"
    assert body["service"] == "director-graph"


def test_run_dry_profile(dg_client):
    request, project = dg_client
    payload = json.dumps({
        "profile_id": "dry-run-audit",
        "project_path": str(project),
        "dry_run": True,
        "auto_approve": True,
    }).encode()
    status, body = request("POST", "/run", payload)
    assert status == 200
    assert body["ok"] is True
    assert body["state"]["review_summary"]["shot_count"] == 1