"""HTTP smoke: director-graph /health + /run on a mini project (S7)."""

from __future__ import annotations

import json
import sys
import threading
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "director-graph"))
sys.path.insert(0, str(ROOT))

from server import DirectorGraphHandler  # noqa: E402


def _mini_project(root: Path) -> Path:
    project = root / "dg_smoke"
    (project / "analysis").mkdir(parents=True, exist_ok=True)
    shot_graph = {
        "schema": "lookbook.shot_graph.v0.3",
        "total_shots": 1,
        "shots": [{
            "shot_index": 0,
            "scene_index": 0,
            "type": "establishing",
            "duration_seconds": 4.0,
            "camera": "pan right",
            "characters": ["Hero"],
            "motion_directive": "Hero enters frame.",
            "panels": [0],
        }],
    }
    (project / "analysis" / "shot_graph.json").write_text(
        json.dumps(shot_graph), encoding="utf-8"
    )
    return project


def main() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        project = _mini_project(Path(tmp))
        server = HTTPServer(("127.0.0.1", 0), DirectorGraphHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"

        import urllib.request

        health = json.loads(
            urllib.request.urlopen(f"{base}/health", timeout=5).read().decode()
        )
        if health.get("status") != "ok":
            server.shutdown()
            return 1

        body = json.dumps({
            "profile_id": "dry-run-audit",
            "project_path": str(project),
            "dry_run": True,
            "auto_approve": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/run",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        result = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        server.shutdown()

    if not result.get("ok"):
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1

    summary = (result.get("state") or {}).get("review_summary") or {}
    print(json.dumps({
        "health": health.get("service"),
        "profile_id": result.get("profile_id"),
        "shot_count": summary.get("shot_count"),
        "director_target": summary.get("director_target"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())