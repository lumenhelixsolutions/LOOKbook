"""lookBOOK → CineForge shot graph handoff (file export + optional HTTP ingest)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..models import write_json
from ..schemas import ShotGraph
from .common import resolve_shot_graph

CINEFORGE_EXPORT_SCHEMA = "lookbook.cineforge_export.v1"
DEFAULT_CINEFORGE_URL = "http://127.0.0.1:8765"
LOOKBOOK_SHOT_GRAPH_SCHEMA = "lookbook.shot_graph.v0.3"


def _load_choreography_assets(project: Path) -> tuple[dict[str, Any] | None, list[Any] | None]:
    """Load choreography + panel list when analysis/choreography.json exists."""
    choreo_path = project / "analysis" / "choreography.json"
    if not choreo_path.exists():
        return None, None
    choreography = json.loads(choreo_path.read_text(encoding="utf-8"))
    panels: list[Any] | None = None
    panel_path = project / "analysis" / "panel_analysis.json"
    if panel_path.exists():
        panel_data = json.loads(panel_path.read_text(encoding="utf-8"))
        raw_panels = panel_data.get("panels")
        if isinstance(raw_panels, list):
            panels = raw_panels
    return choreography, panels


class CineforgeIngestError(RuntimeError):
    """HTTP or API error when pushing to CineForge."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _relative_shot_graph_path(project: Path, graph_path: Path) -> str:
    try:
        rel = graph_path.resolve().relative_to(project.resolve())
        return rel.as_posix()
    except ValueError:
        return Path(graph_path).as_posix()


def _validate_shot_graph(raw: dict[str, Any]) -> dict[str, Any]:
    graph = ShotGraph.model_validate(raw)
    if not graph.shots:
        raise ValueError("Shot graph must contain at least one shot.")
    payload = graph.model_dump(by_alias=True, exclude_none=True)
    schema = str(payload.get("schema") or "")
    if schema and LOOKBOOK_SHOT_GRAPH_SCHEMA not in schema:
        raise ValueError(f"Unsupported shot graph schema: {schema}")
    if "schema" not in payload:
        payload["schema"] = LOOKBOOK_SHOT_GRAPH_SCHEMA
    return payload


def prepare_cineforge_payload(
    project: str | Path,
    shot_graph_path: str | Path | None = None,
    *,
    replace_existing_shots: bool = True,
) -> tuple[dict[str, Any], Path, str]:
    """Resolve and validate shot graph; return CineForge ingest request body."""
    project = Path(project)
    graph_path, raw = resolve_shot_graph(project, shot_graph_path)
    shot_graph = _validate_shot_graph(raw)
    ingest_body: dict[str, Any] = {
        "shot_graph": shot_graph,
        "replace_existing_shots": replace_existing_shots,
    }
    choreography, panels = _load_choreography_assets(project)
    if choreography is not None:
        ingest_body["choreography"] = choreography
    if panels is not None:
        ingest_body["panels"] = panels
    rel_path = _relative_shot_graph_path(project, graph_path)
    return ingest_body, graph_path, rel_path


def export_cineforge_file(
    project: str | Path,
    output: str | Path | None = None,
    shot_graph_path: str | Path | None = None,
    *,
    replace_existing_shots: bool = True,
) -> dict[str, Any]:
    """Write ingest-ready JSON wrapper to exports/cineforge/ingest.json."""
    project = Path(project)
    ingest_body, graph_path, rel_path = prepare_cineforge_payload(
        project,
        shot_graph_path,
        replace_existing_shots=replace_existing_shots,
    )
    out_path = Path(output) if output else project / "exports" / "cineforge" / "ingest.json"
    wrapper = {
        "schema": CINEFORGE_EXPORT_SCHEMA,
        "shot_graph": ingest_body["shot_graph"],
        "replace_existing_shots": ingest_body["replace_existing_shots"],
        "source_project": str(project.resolve()),
        "shot_graph_path": rel_path,
    }
    if "choreography" in ingest_body:
        wrapper["choreography"] = ingest_body["choreography"]
    if "panels" in ingest_body:
        wrapper["panels"] = ingest_body["panels"]
    write_json(out_path, wrapper)
    shots = ingest_body["shot_graph"].get("shots", [])
    return {
        "output_path": out_path,
        "shot_graph_path": graph_path,
        "shot_count": len(shots),
        "ingest_body": ingest_body,
    }


def push_cineforge_ingest(
    payload: dict[str, Any],
    base_url: str,
    project_id: str,
    *,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST shot graph to CineForge ingest API."""
    if not project_id or not str(project_id).strip():
        raise ValueError("--project-id is required when using --push")

    url = f"{base_url.rstrip('/')}/projects/{project_id}/ingest/lookbook"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = detail
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                message = str(parsed.get("detail") or parsed)
        except json.JSONDecodeError:
            pass
        raise CineforgeIngestError(
            f"CineForge ingest failed ({exc.code}): {message}",
            status_code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise CineforgeIngestError(
            f"Could not reach CineForge at {base_url}: {exc.reason}",
        ) from exc


def export_cineforge(
    project: str | Path,
    output: str | Path | None = None,
    shot_graph_path: str | Path | None = None,
    *,
    replace_existing_shots: bool = True,
    push: bool = False,
    cineforge_url: str | None = None,
    project_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Export file (default) and optionally push to a running CineForge API."""
    file_result = export_cineforge_file(
        project,
        output=output,
        shot_graph_path=shot_graph_path,
        replace_existing_shots=replace_existing_shots,
    )
    result = dict(file_result)
    result["pushed"] = False

    if push:
        base_url = cineforge_url or os.environ.get("CINEFORGE_URL") or DEFAULT_CINEFORGE_URL
        key = api_key or os.environ.get("CINEFORGE_API_KEY")
        ingest_response = push_cineforge_ingest(
            file_result["ingest_body"],
            base_url,
            project_id or "",
            api_key=key,
        )
        result["pushed"] = True
        result["cineforge_url"] = base_url
        result["cineforge_project_id"] = project_id
        result["ingest_response"] = ingest_response

    return result