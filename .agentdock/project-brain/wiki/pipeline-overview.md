# lookBOOK Pipeline Overview

Timestamp: 2026-06-12T20:00:00Z
Schema: lookbook.pipeline-overview.v1
Milestone: M6 — CineForge bridge

Animation compiler: source material → scene/shot graph → platform exports and downstream handoffs.

## Pipeline Stages

| Stage | Module | Input → Output | Status |
|-------|--------|----------------|--------|
| 1. Ingest | `pipeline/analyze.py`, `pipeline/ocr.py` | PDF/image/archive → `analysis/` text + panels | production |
| 2. Structure | `pipeline/scene_graph.py`, `pipeline/shot_graph.py` | panels + text → `analysis/scene_graph.json`, `analysis/shot_graph.json` | production |
| 3. Vision path | `pipeline/vision_enhanced.py` | same sources → `*_vision.json` variants (cloud vision LLM) | production |
| 4. Characters | `pipeline/characters.py` | analysis → character registry JSON | production |
| 5. Director packet | `pipeline/director_ai.py` | shot graph → director manifest | production |
| 6. Export | `pipeline/*_export.py` | shot graph → platform manifests (Runway, Veo, Kling, ComfyUI, FFmpeg, Remotion, web) | production |
| 7. CineForge handoff | `pipeline/cineforge_export.py` | shot graph → `exports/cineforge/ingest.json` or HTTP push | production (M6) |
| 8. Animatic | `video/animatic.py` | frames + timing → preview video | experimental |

Classical path: `lookbook analyze` → `build-shot-graph` → export commands.
Vision path: `lookbook analyze-vision` → `build-shot-graph-vision` → exports.

## Inputs and Outputs

**Inputs:** PDFs, image folders, comic archives, plain text, video (vision path).

**Core artifacts:**
- `analysis/shot_graph.json` — canonical `lookbook.shot_graph.v0.3` (Pydantic in `lookbook/schemas.py`)
- `analysis/shot_graph_vision.json` — vision-enhanced graph when used
- `exports/<platform>/` — per-backend manifests
- `exports/cineforge/ingest.json` — CineForge ingest wrapper (`lookbook.cineforge_export.v1`)

## Prompt and Manifest Flow

1. Shot graph encodes panels, camera, motion hints, and style tags per shot.
2. Export modules map shots → provider-specific prompt/manifest JSON (Runway, Veo, Kling, etc.).
3. `director_ai` produces a consolidated director packet for human review before generation.
4. CineForge export validates via `ShotGraph` model, then wraps `{ shot_graph, replace_existing_shots }`.

## Generation Backends

| Backend | Export module | Notes |
|---------|---------------|-------|
| Runway | `runway_export.py` | Gen-3 style manifests |
| Google Veo | `veo_export.py` | Vertex / API prompts |
| Kling | `kling_export.py` | Image-to-video packets |
| ComfyUI | `comfyui_export.py` | Workflow JSON |
| FFmpeg | `ffmpeg_export.py` | Local stitch instructions |
| Remotion | `remotion_export.py` | React timeline props |
| Web gallery | `export_web.py` | Static review site |

Cloud vision APIs are primary for the vision path; local llama.cpp multimodal is experimental (portfolio Phase 1 ⚠️).

## Export Surfaces

**CLI:** `lookbook export-cineforge`, `export-runway`, `export-veo`, etc. (see `lookbook/cli.py`).

**CineForge bridge:**
- File: `lookbook export-cineforge --project <path>` → `exports/cineforge/ingest.json`
- Push: `--push --cineforge-url http://127.0.0.1:8765 --project-id <uuid>`

**Downstream:** `POST /projects/{id}/ingest/lookbook` on CineForge (see cineforge `backend/ingest/lookbook.py`).

## Last Verified End-to-End Run

- **Unit:** `pytest tests/test_cineforge_export.py -q` — export payload validates against `ShotGraph`
- **Schema:** `lookbook.shot_graph.v0.3` round-trips through Pydantic
- **Unverified:** Live `--push` against running CineForge; portfolio script `scripts/pipeline-visual-story.ps1`

## Manual Intervention Required

- Vision path: API keys for cloud vision providers
- CineForge `--push`: running backend + known `project_id`
- Platform exports: provider accounts and rate limits per backend

## Do Not Break

- `lookbook/schemas.py` — `ShotGraph` contract shared with CineForge ingest
- `pipeline/cineforge_export.py` — M6 portfolio bridge
- `resolve_shot_graph()` in `pipeline/common.py` — graph resolution order