"""NOTEtoolsLM / portfolio vault → lookBOOK source handoff."""

from __future__ import annotations

import base64
import json
import re
import shutil
from pathlib import Path
from typing import Any

from ..models import write_json
from ..project import init_project

SOURCE_MANIFEST_SCHEMA = "lookbook.source_manifest.v1"
VAULT_IMPORT_SCHEMA = "lookbook.vault_import.v1"
IMAGE_KINDS = frozenset({"png", "jpg", "jpeg", "webp", "gif"})
IMAGE_SUFFIX = {kind: f".{kind}" if kind != "jpeg" else ".jpg" for kind in IMAGE_KINDS}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "source").lower()).strip("-")
    return slug[:60] or "source"


def _validate_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    fmt = str(raw.get("format") or "")
    if fmt != SOURCE_MANIFEST_SCHEMA:
        raise ValueError(f"Expected format {SOURCE_MANIFEST_SCHEMA}, got {fmt!r}")
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("source manifest must include a non-empty files array")
    for idx, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise ValueError(f"files[{idx}] must be an object")
        kind = str(entry.get("kind") or "md").lower()
        content = entry.get("content")
        content_b64 = entry.get("content_base64")
        if kind in IMAGE_KINDS:
            if not str(content_b64 or content or "").strip():
                raise ValueError(f"files[{idx}] image must include content_base64 or base64 content")
        elif content is None or not str(content).strip():
            raise ValueError(f"files[{idx}] must include non-empty content")
    return raw


def import_vault_manifest(
    project: str | Path,
    manifest: dict[str, Any] | str | Path,
    *,
    init_if_missing: bool = True,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Apply lookbook.source_manifest.v1 into project/source/ and record import metadata."""
    project_path = Path(project)
    if isinstance(manifest, (str, Path)) and Path(manifest).exists():
        raw = json.loads(Path(manifest).read_text(encoding="utf-8"))
    elif isinstance(manifest, (str, Path)):
        raw = json.loads(str(manifest))
    else:
        raw = manifest

    validated = _validate_manifest(raw)
    if not project_path.exists():
        if not init_if_missing:
            raise FileNotFoundError(f"Project not found: {project_path}")
        init_project(project_path, project_name or validated.get("title") or project_path.name)

    source_dir = project_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, str]] = []

    primary_image: Path | None = None
    for entry in validated["files"]:
        name = str(entry.get("name") or f"{_slugify(validated.get('title'))}.md")
        kind = str(entry.get("kind") or "md").lower()
        rel_name = Path(name).name
        if kind in IMAGE_KINDS:
            if not any(rel_name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
                rel_name = f"{rel_name}{IMAGE_SUFFIX.get(kind, '.png')}"
            raw = entry.get("content_base64") or entry.get("content") or ""
            if isinstance(raw, str) and raw.startswith("data:") and "," in raw:
                raw = raw.split(",", 1)[1]
            try:
                payload = base64.b64decode(str(raw), validate=False)
            except Exception as exc:
                raise ValueError(f"files[{rel_name}] image content must be base64") from exc
            if not payload:
                raise ValueError(f"files[{rel_name}] image payload is empty")
            dest = source_dir / rel_name
            dest.write_bytes(payload)
            if primary_image is None:
                primary_image = dest
        else:
            if kind == "md" and not rel_name.lower().endswith(".md"):
                rel_name = f"{rel_name}.md"
            dest = source_dir / rel_name
            dest.write_text(str(entry.get("content") or ""), encoding="utf-8")
        written.append({"name": rel_name, "path": dest.as_posix(), "kind": kind})

    if primary_image is not None:
        shutil.copy2(primary_image, project_path / "source.png")
        written.append({
            "name": "source.png",
            "path": (project_path / "source.png").as_posix(),
            "kind": "png",
            "linked_from": primary_image.name,
        })

    record = {
        "schema": VAULT_IMPORT_SCHEMA,
        "source_manifest": SOURCE_MANIFEST_SCHEMA,
        "title": validated.get("title"),
        "source_type": validated.get("source_type", "research"),
        "files_written": written,
        "metadata": validated.get("metadata") or {},
    }
    write_json(project_path / "analysis" / "vault_import.json", record)
    return {
        "project": str(project_path.resolve()),
        "files_written": len(written),
        "record_path": str((project_path / "analysis" / "vault_import.json").resolve()),
        "written": written,
    }