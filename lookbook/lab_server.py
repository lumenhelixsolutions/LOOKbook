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
  POST /api/director      — generate director decisions
  POST /api/animatic      — generate animatic MP4 from shot JSON
  GET  /api/animatic/{id} — download generated animatic MP4
  GET  /                  — demo-lab UI (index.html)
  GET  /health            — server health check
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
from threading import Thread

from .project import init_project
from .config import get_api_key, get_config
from .director_graph_client import probe_director_graph, run_director_graph
from .lab_capabilities import get_lab_capabilities
from .pipeline.analyze import analyze_source
from .pipeline.characters import extract_characters
from .pipeline.choreography import build_choreography
from .pipeline.ocr import extract_text
from .pipeline.panels import detect_panels
from .pipeline.scene_graph import build_scene_graph
from .pipeline.shot_graph import build_shot_graph
from .pipeline.vision_enhanced import (
    analyze_source_vision,
    build_scene_graph_vision,
    extract_characters_vision,
)
from .pipeline.director_ai import export_director_packet, generate_director_decisions
from .pipeline.living_panels_export import export_living_panels
from .pipeline.cineforge_export import CineforgeIngestError, export_cineforge
from .pipeline.vault_import import import_vault_manifest
from .models import write_json
from .video.animatic import build_animatic
from .schemas import DirectorRequest, AnimaticRequest, ShotGraph

logger = logging.getLogger("lookbook.lab_server")

PROJECTS_ROOT = Path(tempfile.gettempdir()) / "lookbook_lab_projects"
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_LAB_ROOT = REPO_ROOT / "demo-lab"
DEMO_LAB_REACT_ROOT = REPO_ROOT / "demo-lab-react" / "dist"

MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _resolve_static_under(root: Path, url_path: str, *, prefix: str = "") -> Path | None:
    """Map a URL path to a file under root (path traversal safe)."""
    if not root.is_dir():
        return None
    clean = url_path.split("?", 1)[0]
    if prefix and clean.startswith(prefix):
        clean = clean[len(prefix) :]
    if clean in ("", "/"):
        clean = "/index.html"
    if not clean.startswith("/"):
        clean = "/" + clean
    rel = Path(clean.lstrip("/"))
    if ".." in rel.parts:
        return None
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def _resolve_demo_lab_file(url_path: str) -> Path | None:
    """Map a URL path to a file under demo-lab/ (path traversal safe)."""
    clean = url_path.split("?", 1)[0]
    if clean.startswith("/demo-lab/"):
        return _resolve_static_under(DEMO_LAB_ROOT, url_path, prefix="/demo-lab")
    return _resolve_static_under(DEMO_LAB_ROOT, url_path)


def _resolve_demo_lab_react_file(url_path: str) -> Path | None:
    """Map /react/* to demo-lab-react/dist (Vite build)."""
    return _resolve_static_under(DEMO_LAB_REACT_ROOT, url_path, prefix="/react")


def _serve_static_file(handler, file_path: Path):
    body = file_path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", _STATIC_TYPES.get(file_path.suffix.lower(), "application/octet-stream"))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _json_response(handler, status: int, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _safe_project_dir(project_id: str) -> Path:
    """Return a project directory inside PROJECTS_ROOT, rejecting path traversal."""
    if not project_id:
        raise ValueError("project_id is required")
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise ValueError("Invalid project_id")
    project_dir = PROJECTS_ROOT / project_id
    try:
        resolved = project_dir.resolve()
        root_resolved = PROJECTS_ROOT.resolve()
        if not str(resolved).startswith(str(root_resolved)):
            raise ValueError("Path traversal detected")
    except (OSError, RuntimeError):
        raise ValueError("Invalid project path")
    return project_dir


def _check_body_size(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length > MAX_BODY_SIZE:
        raise ValueError(f"Request body too large: {length} bytes (max {MAX_BODY_SIZE})")
    return length


_SOURCE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _find_project_source_image(project_dir: Path) -> Path | None:
    """Locate pipeline image without mutating the project."""
    root_img = project_dir / "source.png"
    if root_img.is_file() and root_img.stat().st_size > 0:
        return root_img
    source_dir = project_dir / "source"
    if source_dir.is_dir():
        for path in sorted(source_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in _SOURCE_IMAGE_SUFFIXES:
                return path
    return None


def _resolve_project_source_image(project_dir: Path) -> Path | None:
    """First pipeline image: source.png, then first image under source/."""
    found = _find_project_source_image(project_dir)
    if found is None:
        return None
    root_img = project_dir / "source.png"
    if found.resolve() != root_img.resolve():
        shutil.copy2(found, root_img)
    return root_img


def _read_multipart_image(handler, project_id: str | None = None) -> tuple[Path, Path]:
    """Naive multipart parser that extracts the first file upload."""
    content_type = handler.headers.get("Content-Type", "")
    if "boundary=" not in content_type:
        raise ValueError("Missing boundary")
    boundary = content_type.split("boundary=")[1].encode()
    length = _check_body_size(handler)
    data = handler.rfile.read(length)

    parts = data.split(b"--" + boundary)
    for part in parts:
        if b'Content-Disposition: form-data; name="file"' in part or b"filename=" in part:
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            file_data = part[header_end + 4 :].rstrip(b"\r\n")
            if not file_data:
                continue
            if project_id:
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    raise ValueError("Project not found")
            else:
                project_id = str(uuid.uuid4())[:8]
                project_dir = PROJECTS_ROOT / project_id
                project_dir.mkdir(parents=True, exist_ok=True)
                init_project(project_dir, f"lab-{project_id}")
            img_path = project_dir / "source.png"
            img_path.write_bytes(file_data)
            return img_path, project_dir
    raise ValueError("No file found in upload")


def _read_pipeline_source(handler, project_id: str | None = None) -> tuple[Path, Path]:
    """Upload file when present; otherwise reuse imported project source image."""
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", 0))

    if "multipart/form-data" in content_type and length > 0 and "boundary=" in content_type:
        try:
            return _read_multipart_image(handler, project_id=project_id)
        except ValueError as exc:
            if str(exc) != "No file found in upload":
                raise

    if project_id:
        project_dir = _safe_project_dir(project_id)
        if not project_dir.exists():
            raise ValueError("Project not found")
        img_path = _resolve_project_source_image(project_dir)
        if img_path:
            return img_path, project_dir
        raise ValueError(
            "No source image in project — upload a page or import vault manifest with an image file"
        )

    raise ValueError("No file found in upload")


def _synthesize_ocr_from_panels(project_dir: Path) -> list[dict]:
    """Create demo OCR blocks from panel bboxes when Tesseract output is missing."""
    panel_path = project_dir / "analysis" / "panel_analysis.json"
    if not panel_path.exists():
        return []
    panels = json.loads(panel_path.read_text(encoding="utf-8")).get("panels", [])
    samples = [
        ("(No OCR text detected — install Tesseract for real dialogue)", "caption"),
        ("(Sound effect region)", "sfx"),
        ("(Narration box)", "narration"),
    ]
    blocks = []
    for i, panel in enumerate(panels):
        bbox = panel.get("bbox", {})
        text, cls = samples[i % len(samples)]
        blocks.append(
            {
                "text": text,
                "classification": cls,
                "bbox": bbox,
                "conf": 75,
                "block_num": i,
            }
        )
    write_json(
        project_dir / "analysis" / "ocr_result.json",
        {
            "schema": "lookbook.ocr.v0.2",
            "source_file": "source.png",
            "lang": "eng",
            "total_blocks": len(blocks),
            "full_text": " ".join(b["text"] for b in blocks),
            "blocks": blocks,
            "synthesized": True,
        },
    )
    return blocks


def _synthesize_characters_from_panels(project_dir: Path) -> list[dict]:
    """Minimal character map so choreography can assign speakers."""
    panel_path = project_dir / "analysis" / "panel_analysis.json"
    if not panel_path.exists():
        return []
    panels = json.loads(panel_path.read_text(encoding="utf-8")).get("panels", [])
    names = ["Hero", "Ally", "Narrator"]
    characters = []
    for i, name in enumerate(names[: max(1, min(3, len(panels)))]):
        panel_idx = i % len(panels)
        pb = panels[panel_idx].get("bbox", {})
        characters.append(
            {
                "character_id": f"char_{i:03d}",
                "name": name,
                "appearances": 1,
                "panels": [{"panel_index": panel_idx, "bbox": pb}],
            }
        )
    write_json(
        project_dir / "analysis" / "character_analysis.json",
        {"schema": "lookbook.characters.v0.2", "characters": characters, "synthesized": True},
    )
    return characters


def _ensure_choreography_inputs(project_dir: Path) -> None:
    """Guarantee analysis files exist before build_choreography."""
    ocr_path = project_dir / "analysis" / "ocr_result.json"
    blocks: list = []
    if ocr_path.exists():
        try:
            blocks = json.loads(ocr_path.read_text(encoding="utf-8")).get("blocks", [])
        except Exception:
            blocks = []
    if not blocks:
        _synthesize_ocr_from_panels(project_dir)
    char_path = project_dir / "analysis" / "character_analysis.json"
    if not char_path.exists():
        _synthesize_characters_from_panels(project_dir)


def _build_living_panels_review(project_dir: Path) -> Path:
    """Build choreography + living-panels HTML for a lab project."""
    _ensure_choreography_inputs(project_dir)
    build_choreography(project_dir)
    return export_living_panels(project_dir)


def _read_multipart_json(handler) -> dict:
    """Naive multipart parser that extracts the first JSON file upload."""
    content_type = handler.headers.get("Content-Type", "")
    if "boundary=" not in content_type:
        raise ValueError("Missing boundary")
    boundary = content_type.split("boundary=")[1].encode()
    length = _check_body_size(handler)
    data = handler.rfile.read(length)

    parts = data.split(b"--" + boundary)
    for part in parts:
        if b"filename=" in part:
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            file_data = part[header_end + 4 :].rstrip(b"\r\n")
            return json.loads(file_data.decode("utf-8"))
    raise ValueError("No JSON file found in upload")


def _label_characters(characters: list[dict]) -> list[dict]:
    """Attach readable names when clustering did not produce them."""
    for i, char in enumerate(characters):
        if char.get("name"):
            continue
        if len(characters) == 1:
            char["name"] = "Lead character"
        else:
            char["name"] = f"Character {chr(65 + (i % 26))}"
    return characters


def _interpret_project(project_dir: Path, use_vision: bool = False) -> dict:
    """Run real page interpretation: characters, scenes, choreography, shots."""
    source = project_dir / "source.png"
    summary: dict = {
        "method": "classical",
        "characters": [],
        "scenes": [],
        "page_description": None,
        "shot_graph": False,
        "choreography_lines": 0,
        "vision_available": False,
    }

    try:
        summary["characters"] = _label_characters(extract_characters(source, project_dir))
        write_json(
            project_dir / "analysis" / "character_analysis.json",
            {
                "schema": "lookbook.characters.v0.2",
                "source_file": source.name,
                "total_characters": len(summary["characters"]),
                "characters": summary["characters"],
            },
        )
    except Exception as exc:
        logger.warning("Character extraction failed: %s", exc)
        summary["characters"] = _label_characters(_synthesize_characters_from_panels(project_dir))
        summary["characters_fallback"] = True

    try:
        summary["scenes"] = build_scene_graph(project_dir)
    except Exception as exc:
        logger.warning("Scene graph failed: %s", exc)
        summary["scenes"] = []

    try:
        _ensure_choreography_inputs(project_dir)
        lines = build_choreography(project_dir)
        summary["choreography_lines"] = len(lines)
    except Exception as exc:
        logger.warning("Choreography failed: %s", exc)

    try:
        build_shot_graph(project_dir)
        summary["shot_graph"] = True
    except Exception as exc:
        logger.warning("Shot graph failed: %s", exc)

    page_notes: list[str] = []
    for scene in summary["scenes"][:3]:
        bits = []
        if scene.get("dialogue"):
            bits.append("Dialogue: " + "; ".join(scene["dialogue"][:4]))
        if scene.get("narration"):
            bits.append("Narration: " + "; ".join(scene["narration"][:2]))
        if bits:
            page_notes.append(f"Scene {scene.get('scene_index', 0)}: " + " · ".join(bits))
    if page_notes:
        summary["page_description"] = " ".join(page_notes)

    if use_vision:
        provider = get_config()["vision"]["provider"]
        if get_api_key(provider):
            summary["vision_available"] = True
            try:
                vision_page = analyze_source_vision(source, project_dir, provider=provider)
                desc = vision_page.get("description") or vision_page.get("raw") or str(vision_page)
                summary["page_description"] = str(desc)[:2000]
                summary["method"] = "vision"
                vchars = extract_characters_vision(project_dir, provider=provider)
                if vchars:
                    summary["characters"] = vchars
                build_scene_graph_vision(project_dir, provider=provider)
            except Exception as exc:
                logger.warning("Vision interpret failed: %s", exc)
                summary["vision_error"] = str(exc)
        else:
            summary["vision_skipped"] = (
                f"Vision requested but no API key for {provider} — "
                "set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY"
            )
    else:
        summary["vision_skipped"] = (
            "Vision disabled in Settings — classical scene summary used."
        )

    write_json(
        project_dir / "analysis" / "page_interpretation.json",
        {
            "schema": "lookbook.page_interpretation.v1",
            "method": summary["method"],
            "page_description": summary.get("page_description"),
            "total_characters": len(summary["characters"]),
            "total_scenes": len(summary["scenes"]),
            "choreography_lines": summary["choreography_lines"],
            "shot_graph": summary["shot_graph"],
            "vision_available": summary.get("vision_available", False),
            "vision_error": summary.get("vision_error"),
            "vision_skipped": summary.get("vision_skipped"),
        },
    )
    return summary


def _run_lab_pipeline(
    project_dir: Path,
    img_path: Path,
    use_vision: bool = False,
) -> dict:
    """Single server-side pipeline: panels → OCR → interpret. No browser sync."""
    caps = get_lab_capabilities()
    if not caps["ready_for_pipeline"]:
        raise RuntimeError(
            "Lab not ready: " + "; ".join(caps["notes"][:3])
        )

    analyze_source(img_path, project_dir)
    panels = detect_panels(img_path, project_dir)

    ocr_error = None
    ocr_fallback = False
    try:
        ocr_blocks = extract_text(img_path, project_dir)
    except Exception as exc:
        ocr_error = str(exc)
        ocr_fallback = True
        ocr_blocks = _synthesize_ocr_from_panels(project_dir)

    interpretation = _interpret_project(project_dir, use_vision=use_vision)

    ocr_path = project_dir / "analysis" / "ocr_result.json"
    ocr_payload = {}
    if ocr_path.exists():
        try:
            ocr_payload = json.loads(ocr_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "panels": panels,
        "panel_count": len(panels),
        "ocr_blocks": ocr_blocks,
        "ocr_fallback": ocr_fallback,
        "ocr_error": ocr_error,
        "ocr_synthesized": bool(ocr_payload.get("synthesized")),
        "interpretation": interpretation,
        "capabilities": caps,
    }


def _director_graph_record(project_dir: Path) -> dict:
    path = project_dir / "analysis" / "director_graph_run.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _invoke_director_graph_for_project(
    project_dir: Path,
    *,
    profile_id: str = "classical-runway",
    dry_run: bool = False,
    target: str | None = None,
) -> dict:
    probe = probe_director_graph()
    if not probe.get("online"):
        raise RuntimeError(
            "Director graph sidecar offline — run: python director-graph/server.py"
        )
    result = run_director_graph(
        str(project_dir.resolve()),
        profile_id=profile_id,
        auto_approve=True,
        dry_run=dry_run,
        target=target,
    )
    review = (result.get("state") or {}).get("review_summary") or {}
    write_json(
        project_dir / "analysis" / "director_graph_run.json",
        {
            "schema": "lookbook.director_graph_run.v1",
            "ok": bool(result.get("ok")),
            "profile_id": profile_id,
            "dry_run": dry_run,
            "review_summary": review,
            "error": result.get("error"),
        },
    )
    return result


def _lab_director_markdown(project_dir: Path, target: str) -> str:
    """Director preview from interpreted scene/character data (no shot graph required)."""
    panel_count = 0
    panel_path = project_dir / "analysis" / "panel_analysis.json"
    if panel_path.exists():
        try:
            panel_count = json.loads(panel_path.read_text(encoding="utf-8")).get("total_panels", 0)
        except Exception:
            pass

    interpret_path = project_dir / "analysis" / "page_interpretation.json"
    interpret = {}
    if interpret_path.exists():
        try:
            interpret = json.loads(interpret_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    char_lines = []
    char_path = project_dir / "analysis" / "character_analysis.json"
    if char_path.exists():
        try:
            for c in json.loads(char_path.read_text(encoding="utf-8")).get("characters", [])[:6]:
                name = c.get("name") or c.get("character_id", "character")
                desc = c.get("description", "")
                apps = c.get("appearances", len(c.get("panels", [])))
                line = f"- **{name}** — {apps} panel appearance(s)"
                if desc:
                    line += f": {desc[:160]}"
                char_lines.append(line)
        except Exception:
            pass

    scene_lines = []
    scene_path = project_dir / "analysis" / "scene_graph.json"
    if scene_path.exists():
        try:
            for s in json.loads(scene_path.read_text(encoding="utf-8")).get("scenes", [])[:4]:
                dlg = "; ".join(s.get("dialogue", [])[:3]) or "(no dialogue)"
                nar = "; ".join(s.get("narration", [])[:2])
                scene_lines.append(
                    f"- **Scene {s.get('scene_index', 0)}** ({s.get('panel_count', 0)} panels): {dlg}"
                    + (f" · _{nar}_" if nar else "")
                )
        except Exception:
            pass

    page_desc = interpret.get("page_description") or "Run the pipeline to interpret this page."
    method = interpret.get("method", "classical")

    return (
        f"# Director AI Packet — {target.upper()} (lab)\n\n"
        "## Page read\n"
        f"{page_desc}\n\n"
        f"**Interpretation:** {method} · **Panels:** {panel_count} · "
        f"**Choreography lines:** {interpret.get('choreography_lines', 0)}\n\n"
        "## Characters\n"
        + ("\n".join(char_lines) if char_lines else "- (none tracked yet)\n")
        + "\n\n## Scenes\n"
        + ("\n".join(scene_lines) if scene_lines else "- (no scene breakdown yet)\n")
        + "\n\n## Next\n"
        "Use **Living panels → Play** for timed dialogue playback. "
        "Enable **vision LLM** in Settings for richer semantic descriptions.\n"
    )


def _living_panels_project_id(path: str) -> str:
    """Extract project id from /api/living-panels/{id}."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "living-panels":
        return parts[2]
    return path.split("/")[-1]


def _project_file_parts(path: str) -> tuple[str, str] | None:
    """Parse /api/project/{id}/file/{relpath} into (project_id, relpath)."""
    parts = [p for p in path.split("/") if p]
    if len(parts) < 5 or parts[0] != "api" or parts[1] != "project" or parts[3] != "file":
        return None
    return parts[2], "/".join(parts[4:])


def _rewrite_living_panels_html_for_api(html: str, project_id: str) -> bytes:
    """Fix relative panel image paths when review.html is served under /api/living-panels/."""
    asset_base = f"/api/project/{project_id}/file/"
    for prefix in ("../../analysis/", "../analysis/"):
        html = html.replace(prefix, f"{asset_base}analysis/")
    return html.encode("utf-8")


def _serve_project_file(handler, project_dir: Path, relpath: str) -> None:
    """Stream a file from a lab project directory (path-traversal safe)."""
    rel = Path(relpath.replace("\\", "/"))
    if not relpath or ".." in rel.parts:
        _json_response(handler, 400, {"error": "Invalid file path"})
        return
    candidate = (project_dir / rel).resolve()
    root = project_dir.resolve()
    if not str(candidate).startswith(str(root)):
        _json_response(handler, 403, {"error": "Permission denied"})
        return
    if not candidate.is_file():
        _json_response(handler, 404, {"error": "File not found"})
        return
    body = candidate.read_bytes()
    handler.send_response(200)
    handler.send_header(
        "Content-Type",
        _STATIC_TYPES.get(candidate.suffix.lower(), "application/octet-stream"),
    )
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _placeholder_living_panels_html(project_dir: Path, message: str) -> Path:
    """In-iframe placeholder when review cannot be built yet."""
    out = project_dir / "exports" / "living_panels" / "review.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"""<!doctype html><html><head><meta charset="utf-8"><title>Living Panels</title>
<style>body{{font-family:system-ui;background:#12100e;color:#f5e6d0;padding:32px;text-align:center}}
.box{{max-width:420px;margin:40px auto;padding:24px;border:1px dashed #ffb04244;border-radius:16px}}
</style></head><body><div class="box"><h2>Living panels not ready</h2><p>{message}</p>
<p style="color:#f5e6d088;font-size:14px">Use <strong>Build &amp; play living panels</strong> in the lab above.</p></div></body></html>""",
        encoding="utf-8",
    )
    return out


def _seed_project_preset(project_dir: Path, preset: str) -> dict:
    """Seed analysis/ layout for demo-lab wizard presets."""
    analysis = project_dir / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    scaffold = {
        "schema": "lookbook.project_scaffold.v1",
        "preset": preset,
        "folders": ["analysis", "source", "exports"],
    }
    scaffold_path = analysis / "project_scaffold.json"
    scaffold_path.write_text(json.dumps(scaffold, indent=2), encoding="utf-8")
    (project_dir / "source").mkdir(parents=True, exist_ok=True)
    (project_dir / "exports").mkdir(parents=True, exist_ok=True)
    return {"preset": preset, "scaffold_path": str(scaffold_path)}


def _read_json_body(handler) -> dict:
    """Read and validate a JSON body for non-multipart POSTs."""
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        raise ValueError("Content-Type must be application/json")
    length = _check_body_size(handler)
    data = handler.rfile.read(length)
    if not data:
        raise ValueError("Empty request body")
    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle concurrent lab requests so living-panels builds do not block /health."""

    daemon_threads = True


class LabHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.info(fmt % args)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/health":
                caps = get_lab_capabilities()
                dg = probe_director_graph()
                caps["director_graph"] = bool(dg.get("online"))
                caps["director_graph_url"] = dg.get("url")
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "service": "lookbook-lab",
                        "version": 5,
                        "features": [
                            "pipeline-run",
                            "living-panels-build",
                            "interpret-page",
                            "director-graph-run",
                            "demo-lab-react",
                        ],
                        "capabilities": caps,
                    },
                )
                return

            if path.startswith("/api/director-preview/"):
                project_id = path.split("/")[-1]
                query = parse_qs(parsed.query)
                target = query.get("target", ["runway"])[0]
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                graph_record = _director_graph_record(project_dir)
                graph_ok = bool(graph_record.get("ok"))
                out_dir = project_dir / "exports" / "director_ai"
                md_files = list(out_dir.glob("*.md")) if out_dir.exists() else []
                md_path = md_files[0] if md_files else None
                source = "lab-stub"
                if not md_path:
                    try:
                        md_path = export_director_packet(project_dir, target=target)
                        markdown = md_path.read_text(encoding="utf-8")
                        source = "director-graph" if graph_ok else "director-ai"
                    except FileNotFoundError:
                        markdown = _lab_director_markdown(project_dir, target=target)
                        md_path = None
                        source = "lab-stub"
                else:
                    markdown = md_path.read_text(encoding="utf-8")
                    source = "director-graph" if graph_ok else "director-ai"
                review = graph_record.get("review_summary") or {}
                _json_response(
                    self,
                    200,
                    {
                        "project_id": project_id,
                        "target": target,
                        "path": md_path.name if md_path else "lab-preview.md",
                        "markdown": markdown,
                        "source": source,
                        "shot_count": review.get("shot_count"),
                        "director_graph": graph_ok,
                    },
                )
                return

            if path.startswith("/api/living-panels/"):
                project_id = _living_panels_project_id(path)
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                review_path = project_dir / "exports" / "living_panels" / "review.html"
                if not review_path.exists():
                    panel_file = project_dir / "analysis" / "panel_analysis.json"
                    if not panel_file.exists():
                        review_path = _placeholder_living_panels_html(
                            project_dir, "Run the pipeline on an image first."
                        )
                    else:
                        try:
                            review_path = _build_living_panels_review(project_dir)
                        except Exception as exc:
                            logger.warning("Living panels build failed: %s", exc)
                            review_path = _placeholder_living_panels_html(
                                project_dir, "Could not build review yet. Try Build &amp; play again."
                            )
                html = review_path.read_text(encoding="utf-8")
                body = _rewrite_living_panels_html_for_api(html, project_id)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            file_parts = _project_file_parts(path)
            if file_parts is not None:
                project_id, relpath = file_parts
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                _serve_project_file(self, project_dir, relpath)
                return

            if path.startswith("/api/project/"):
                project_id = path.split("/")[-1]
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                files = {}
                analysis_dir = project_dir / "analysis"
                if analysis_dir.is_dir():
                    for json_file in analysis_dir.glob("*.json"):
                        try:
                            files[json_file.stem] = json.loads(json_file.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                source_files = []
                if (project_dir / "source.png").is_file():
                    source_files.append("source.png")
                source_dir = project_dir / "source"
                if source_dir.is_dir():
                    for item in sorted(source_dir.iterdir()):
                        if item.is_file() and item.suffix.lower() in _SOURCE_IMAGE_SUFFIXES:
                            rel = item.relative_to(project_dir).as_posix()
                            if rel not in source_files:
                                source_files.append(rel)
                has_source_image = _find_project_source_image(project_dir) is not None
                _json_response(
                    self,
                    200,
                    {
                        "project_id": project_id,
                        "analysis": files,
                        "source_files": source_files,
                        "has_source_image": has_source_image,
                    },
                )
                return

            if path.startswith("/api/export/"):
                project_id = path.split("/")[-1]
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                artifacts = {}
                for platform_dir in (project_dir / "exports").iterdir():
                    if platform_dir.is_dir():
                        artifacts[platform_dir.name] = [f.name for f in platform_dir.iterdir()]
                _json_response(self, 200, {"project_id": project_id, "artifacts": artifacts})
                return

            if path.startswith("/api/animatic/"):
                project_id = path.split("/")[-1]
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                animatic_path = project_dir / "animatic.mp4"
                if not animatic_path.exists():
                    _json_response(self, 404, {"error": "Animatic not found"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(animatic_path.stat().st_size))
                self.end_headers()
                self.wfile.write(animatic_path.read_bytes())
                return

            if path == "/react" or path.startswith("/react/"):
                react_file = _resolve_demo_lab_react_file(
                    path if path.startswith("/react/") else "/react/index.html"
                )
                if react_file is not None:
                    _serve_static_file(self, react_file)
                    return

            static_file = _resolve_demo_lab_file(path)
            if static_file is not None:
                _serve_static_file(self, static_file)
                return

            _json_response(self, 404, {"error": "Not found"})
        except ValueError as exc:
            logger.warning("GET validation error: %s", exc)
            _json_response(self, 400, {"error": str(exc)})
        except Exception as exc:
            logger.exception("Unhandled GET error")
            _json_response(self, 500, {"error": "Internal server error"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/new-project":
                req = _read_json_body(self)
                name = str(req.get("name") or "lab-project").strip()[:60] or "lab-project"
                preset = str(req.get("preset") or "comic").strip()
                project_id = str(uuid.uuid4())[:8]
                project_dir = PROJECTS_ROOT / project_id
                project_dir.mkdir(parents=True, exist_ok=True)
                init_project(project_dir, name)
                seed = _seed_project_preset(project_dir, preset)
                _json_response(
                    self,
                    200,
                    {"project_id": project_id, "name": name, "seed": seed},
                )
                return

            if path == "/api/import-vault":
                req = _read_json_body(self)
                manifest = req.get("manifest")
                if not isinstance(manifest, dict):
                    raise ValueError("manifest object required")
                project_id = req.get("project_id")
                if project_id:
                    project_dir = _safe_project_dir(str(project_id))
                    if not project_dir.exists():
                        _json_response(self, 404, {"error": "Project not found"})
                        return
                else:
                    project_id = str(uuid.uuid4())[:8]
                    project_dir = PROJECTS_ROOT / project_id
                result = import_vault_manifest(
                    project_dir,
                    manifest,
                    init_if_missing=True,
                    project_name=manifest.get("title"),
                )
                _json_response(
                    self,
                    200,
                    {"project_id": project_dir.name, "import": result},
                )
                return

            query = parse_qs(parsed.query)
            existing_project = query.get("project_id", [None])[0]

            if path == "/api/build-living-panels":
                req = _read_json_body(self)
                project_id = str(req.get("project_id") or "")
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                review_path = _build_living_panels_review(project_dir)
                choreo = json.loads(
                    (project_dir / "analysis" / "choreography.json").read_text(encoding="utf-8")
                )
                _json_response(
                    self,
                    200,
                    {
                        "project_id": project_id,
                        "choreography_lines": choreo.get("total_lines", 0),
                        "living_panels_url": f"/api/living-panels/{project_id}",
                        "review_path": str(review_path),
                    },
                )
                return

            if path.startswith("/api/project/") and path.endswith("/sync-analysis"):
                parts = [p for p in path.split("/") if p]
                if len(parts) < 4 or parts[0] != "api" or parts[1] != "project":
                    _json_response(self, 400, {"error": "Invalid sync path"})
                    return
                project_id = parts[2]
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                req = _read_json_body(self)
                if req.get("ocr_blocks"):
                    write_json(
                        project_dir / "analysis" / "ocr_result.json",
                        {
                            "schema": "lookbook.ocr.v0.2",
                            "source_file": "source.png",
                            "lang": "eng",
                            "total_blocks": len(req["ocr_blocks"]),
                            "full_text": " ".join(
                                str(b.get("text", "")) for b in req["ocr_blocks"]
                            ),
                            "blocks": req["ocr_blocks"],
                            "synced_from_lab": True,
                        },
                    )
                if req.get("characters"):
                    chars = []
                    for i, c in enumerate(req["characters"]):
                        panel_indices = c.get("panels") or []
                        char_panels = []
                        panel_file = project_dir / "analysis" / "panel_analysis.json"
                        panel_list = []
                        if panel_file.exists():
                            panel_list = json.loads(
                                panel_file.read_text(encoding="utf-8")
                            ).get("panels", [])
                        for pidx in panel_indices:
                            bbox = {}
                            if panel_list and pidx < len(panel_list):
                                bbox = panel_list[pidx].get("bbox", {})
                            char_panels.append({"panel_index": pidx, "bbox": bbox})
                        chars.append(
                            {
                                "character_id": f"char_{i:03d}",
                                "name": c.get("name", f"Character {i + 1}"),
                                "appearances": len(char_panels),
                                "panels": char_panels,
                            }
                        )
                    write_json(
                        project_dir / "analysis" / "character_analysis.json",
                        {"schema": "lookbook.characters.v0.2", "characters": chars},
                    )
                _json_response(self, 200, {"project_id": project_id, "synced": True})
                return

            if path == "/api/pipeline/run":
                use_vision = query.get("use_vision", ["false"])[0].lower() in ("1", "true", "yes")
                img_path, project_dir = _read_pipeline_source(self, project_id=existing_project)
                try:
                    result = _run_lab_pipeline(project_dir, img_path, use_vision=use_vision)
                except RuntimeError as exc:
                    _json_response(self, 503, {"error": str(exc), "capabilities": get_lab_capabilities()})
                    return
                _json_response(
                    self,
                    200,
                    {"project_id": project_dir.name, "pipeline": result},
                )
                return

            if path == "/api/export-cineforge":
                req = _read_json_body(self)
                project_id = str(req.get("project_id") or "")
                if not project_id:
                    _json_response(self, 400, {"error": "project_id required"})
                    return
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                push = bool(req.get("push"))
                cineforge_url = str(
                    req.get("cineforge_url")
                    or req.get("cineforgeUrl")
                    or os.environ.get("CINEFORGE_URL")
                    or "http://127.0.0.1:8765"
                )
                cineforge_project_id = str(
                    req.get("cineforge_project_id")
                    or req.get("cineforgeProjectId")
                    or ""
                ).strip()
                if push and not cineforge_project_id:
                    _json_response(
                        self,
                        400,
                        {"error": "cineforge_project_id required when push=true"},
                    )
                    return
                try:
                    result = export_cineforge(
                        project_dir,
                        push=push,
                        cineforge_url=cineforge_url,
                        project_id=cineforge_project_id or None,
                    )
                except (ValueError, CineforgeIngestError) as exc:
                    status = 502 if isinstance(exc, CineforgeIngestError) else 400
                    _json_response(self, status, {"error": str(exc)})
                    return
                choreography = None
                ingest_body = result.get("ingest_body") or {}
                if isinstance(ingest_body.get("choreography"), dict):
                    choreography = ingest_body["choreography"]
                _json_response(
                    self,
                    200,
                    {
                        "project_id": project_id,
                        "output_path": str(result.get("output_path") or ""),
                        "shot_count": int(result.get("shot_count") or 0),
                        "pushed": bool(result.get("pushed")),
                        "cineforge_url": result.get("cineforge_url") or cineforge_url,
                        "cineforge_project_id": result.get("cineforge_project_id")
                        or cineforge_project_id
                        or None,
                        "ingest_response": result.get("ingest_response"),
                        "choreography_lines": (
                            int(choreography.get("line_count") or len(choreography.get("lines") or []))
                            if choreography
                            else 0
                        ),
                        "cineforge_ui_url": (
                            f"{cineforge_url.rstrip('/')}/projects/{cineforge_project_id}"
                            if push and cineforge_project_id
                            else None
                        ),
                    },
                )
                return

            if path == "/api/director-graph/run":
                req = _read_json_body(self)
                project_id = str(req.get("project_id") or "")
                if not project_id:
                    _json_response(self, 400, {"error": "project_id required"})
                    return
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                profile_id = str(req.get("profile_id") or "classical-runway")
                dry_run = bool(req.get("dry_run") or req.get("dryRun"))
                target = req.get("target")
                try:
                    result = _invoke_director_graph_for_project(
                        project_dir,
                        profile_id=profile_id,
                        dry_run=dry_run,
                        target=target,
                    )
                except RuntimeError as exc:
                    _json_response(self, 503, {"error": str(exc)})
                    return
                _json_response(
                    self,
                    200 if result.get("ok") else 422,
                    {
                        "project_id": project_id,
                        "ok": bool(result.get("ok")),
                        "profile_id": profile_id,
                        "review_summary": (result.get("state") or {}).get("review_summary"),
                        "error": result.get("error"),
                    },
                )
                return

            if path == "/api/interpret":
                req = _read_json_body(self)
                project_id = str(req.get("project_id") or "")
                use_vision = bool(req.get("use_vision"))
                project_dir = _safe_project_dir(project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                result = _interpret_project(project_dir, use_vision=use_vision)
                _json_response(
                    self,
                    200,
                    {"project_id": project_id, "interpretation": result},
                )
                return

            if path == "/api/analyze":
                img_path, project_dir = _read_multipart_image(self, project_id=existing_project)
                result = analyze_source(img_path, project_dir)
                _json_response(self, 200, {"project_id": project_dir.name, "result": result})
                return

            if path == "/api/extract-text":
                img_path, project_dir = _read_multipart_image(self, project_id=existing_project)
                ocr_error = None
                try:
                    blocks = extract_text(img_path, project_dir)
                except Exception as exc:
                    ocr_error = str(exc)
                    logger.warning("OCR failed: %s", exc)
                    blocks = _synthesize_ocr_from_panels(project_dir)
                _json_response(
                    self,
                    200,
                    {
                        "project_id": project_dir.name,
                        "blocks": blocks,
                        "ocr_fallback": bool(ocr_error),
                        "ocr_error": ocr_error,
                    },
                )
                return

            if path == "/api/panels":
                img_path, project_dir = _read_multipart_image(self, project_id=existing_project)
                panels = detect_panels(img_path, project_dir)
                _json_response(self, 200, {"project_id": project_dir.name, "panels": panels})
                return

            if path == "/api/vision":
                img_path, project_dir = _read_multipart_image(self, project_id=existing_project)
                provider = query.get("provider", [None])[0]
                result = analyze_source_vision(img_path, project_dir, provider=provider)
                _json_response(self, 200, {"project_id": project_dir.name, "result": result})
                return

            if path == "/api/director":
                req = _read_json_body(self)
                validated = DirectorRequest.model_validate(req)
                project_dir = _safe_project_dir(validated.project_id)
                if not project_dir.exists():
                    _json_response(self, 404, {"error": "Project not found"})
                    return
                decision = generate_director_decisions(project_dir, target=validated.target)
                _json_response(self, 200, decision.model_dump())
                return

            if path == "/api/animatic":
                content_type = self.headers.get("Content-Type", "")
                if "multipart/form-data" in content_type:
                    shot_data = _read_multipart_json(self)
                    ShotGraph.model_validate(shot_data)
                    clip_duration = shot_data.get("clip_duration", 3.0)
                else:
                    raw = _read_json_body(self)
                    req = AnimaticRequest.model_validate(raw)
                    if req.project_id:
                        project_dir = _safe_project_dir(req.project_id)
                        if not project_dir.exists():
                            _json_response(self, 404, {"error": "Project not found"})
                            return
                        shot_graph_path = project_dir / "analysis" / "shot_graph.json"
                        if not shot_graph_path.exists():
                            _json_response(self, 404, {"error": "Shot graph not found"})
                            return
                        shot_data = json.loads(shot_graph_path.read_text(encoding="utf-8"))
                        ShotGraph.model_validate(shot_data)
                    elif req.shot_graph:
                        shot_data = req.shot_graph
                        ShotGraph.model_validate(shot_data)
                    else:
                        _json_response(self, 400, {"error": "Missing shot_graph or project_id"})
                        return
                    clip_duration = req.clip_duration

                project_id = str(uuid.uuid4())[:8]
                project_dir = PROJECTS_ROOT / project_id
                project_dir.mkdir(parents=True, exist_ok=True)
                shot_graph_path = project_dir / "shot_graph.json"
                shot_graph_path.write_text(json.dumps(shot_data), encoding="utf-8")

                output_path = project_dir / "animatic.mp4"
                result = build_animatic(
                    shot_graph_path,
                    output_path,
                    clip_duration=clip_duration,
                )
                _json_response(
                    self,
                    200,
                    {
                        "project_id": project_id,
                        "animatic_path": str(output_path),
                        "preview_url": f"/api/animatic/{project_id}",
                        "total_shots": result["total_shots"],
                        "total_duration_seconds": result["total_duration_seconds"],
                    },
                )
                return

            _json_response(self, 404, {"error": "Not found"})
        except ValueError as exc:
            logger.warning("POST validation error: %s", exc)
            msg = str(exc)
            if "too large" in msg.lower():
                _json_response(self, 413, {"error": msg})
            else:
                _json_response(self, 400, {"error": msg})
        except PermissionError as exc:
            logger.warning("POST permission error: %s", exc)
            _json_response(self, 403, {"error": "Permission denied"})
        except Exception as exc:
            logger.exception("Unhandled POST error")
            _json_response(self, 500, {"error": "Internal server error"})


def run_lab_server(port: int = 8042):
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    server = ThreadedHTTPServer(("", port), LabHandler)
    logger.info("lookBOOK Lab Server running at http://localhost:%s", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down lab server.")
        server.shutdown()


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8042
    run_lab_server(port=port)


def start_lab_server_thread(port: int = 8042) -> Thread:
    """Start the lab server in a background thread."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    server = ThreadedHTTPServer(("", port), LabHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("lookBOOK Lab Server running at http://localhost:%s", port)
    return thread


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="lookBOOK Demo Lab server")
    parser.add_argument("--port", type=int, default=8042)
    args = parser.parse_args()
    run_lab_server(port=args.port)
