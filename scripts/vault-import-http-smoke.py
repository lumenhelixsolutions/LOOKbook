"""HTTP smoke: POST /api/import-vault seeds project/source/ (S5)."""

from __future__ import annotations

import json
import sys
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from lookbook.lab_server import LabHandler, PROJECTS_ROOT
from lookbook.pipeline.vault_import import SOURCE_MANIFEST_SCHEMA


def main() -> int:
    manifest_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not manifest_path or not manifest_path.exists():
        print("Usage: python scripts/vault-import-http-smoke.py <manifest.json>", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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

        body = json.dumps({"manifest": manifest}).encode("utf-8")
        req = urllib.request.Request(
            f"http://{host}:{port}/api/import-vault",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode())

        project_id = result.get("project_id")
        files_written = int((result.get("import") or {}).get("files_written") or 0)
        if not project_id or files_written < 1:
            print(json.dumps(result, indent=2), file=sys.stderr)
            server.shutdown()
            return 1

        project_dir = root / project_id
        source_files = list((project_dir / "source").glob("*"))
        record = project_dir / "analysis" / "vault_import.json"
        if not source_files or not record.exists():
            print("source/ or vault_import.json missing", file=sys.stderr)
            server.shutdown()
            return 1

        print(
            json.dumps(
                {
                    "project_id": project_id,
                    "files_written": files_written,
                    "source_files": [p.name for p in source_files],
                    "record_path": str(record),
                }
            )
        )
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())