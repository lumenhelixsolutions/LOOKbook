"""HTTP smoke: vault import → pipeline/run?project_id= (S6)."""

from __future__ import annotations

import base64
import json
import sys
import threading
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from lookbook.lab_server import LabHandler
from lookbook.pipeline.vault_import import SOURCE_MANIFEST_SCHEMA


def _build_manifest_with_image(manifest: dict, image_path: Path) -> dict:
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    out = dict(manifest)
    files = list(out.get("files") or [])
    files.append({
        "name": image_path.name,
        "kind": "png",
        "content_base64": payload,
    })
    out["files"] = files
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "Usage: python scripts/vault-pipeline-http-smoke.py <manifest.json> <image.png>",
            file=sys.stderr,
        )
        return 1

    manifest_path = Path(sys.argv[1])
    image_path = Path(sys.argv[2])
    if not manifest_path.exists() or not image_path.exists():
        print("Manifest or image path missing", file=sys.stderr)
        return 1

    manifest = _build_manifest_with_image(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        image_path,
    )
    if manifest.get("format") != SOURCE_MANIFEST_SCHEMA:
        print(f"Expected {SOURCE_MANIFEST_SCHEMA}", file=sys.stderr)
        return 1

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "lab_projects"
        root.mkdir(parents=True)
        import lookbook.lab_server as lab_mod

        lab_mod.PROJECTS_ROOT = root

        server = HTTPServer(("127.0.0.1", 0), LabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"

        import_body = json.dumps({"manifest": manifest}).encode("utf-8")
        import_req = urllib.request.Request(
            f"{base}/api/import-vault",
            data=import_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        import_resp = urllib.request.urlopen(import_req, timeout=15)
        imported = json.loads(import_resp.read().decode())
        project_id = imported.get("project_id")
        if not project_id:
            server.shutdown()
            return 1

        qs = urllib.parse.urlencode({"project_id": project_id, "use_vision": "false"})
        pipe_req = urllib.request.Request(
            f"{base}/api/pipeline/run?{qs}",
            data=b"",
            headers={"Content-Length": "0"},
            method="POST",
        )
        pipe_resp = urllib.request.urlopen(pipe_req, timeout=60)
        piped = json.loads(pipe_resp.read().decode())

        project_dir = root / project_id
        vault_record = project_dir / "analysis" / "vault_import.json"
        panel_path = project_dir / "analysis" / "panel_analysis.json"
        ocr_path = project_dir / "analysis" / "ocr_result.json"
        pipe = piped.get("pipeline") or {}

        if not vault_record.exists() or not panel_path.exists():
            print("vault_import or panel_analysis missing", file=sys.stderr)
            server.shutdown()
            return 1
        if int(pipe.get("panel_count") or 0) < 1:
            print("pipeline returned no panels", file=sys.stderr)
            server.shutdown()
            return 1

        print(
            json.dumps(
                {
                    "project_id": project_id,
                    "panel_count": pipe.get("panel_count"),
                    "ocr_blocks": len(pipe.get("ocr_blocks") or []),
                    "vault_import": vault_record.exists(),
                    "ocr_result": ocr_path.exists(),
                    "source_reused": True,
                }
            )
        )
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())