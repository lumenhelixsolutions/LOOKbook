# lookBOOK Evolution Milestones

## M1: Vision LLM Integration ✅
- [x] `vision_llm.py` — OpenAI, Claude, Gemini analyzers
- [x] `vision_cache.py` — SHA256 disk cache for API results
- [x] `vision_enhanced.py` — vision-powered characters, scene graph, shot graph
- [x] CLI flags: `--use-vision`, `--vision-provider`
- [x] Archive batch pipeline supports vision

## M2: Scene Understanding & Director AI ✅
- [x] `director_ai.py` — emotional arc inference, pacing notes, camera language
- [x] Platform-specific negative prompts (Runway, Veo, Kling, Pika, Luma)
- [x] Director packet export (`director-ai` CLI command)
- [x] Shot enrichment with director notes

## M3: Export Pipeline 2.0 ✅
- [x] `true_animation_packet.py` — dynamic shot lists from actual shot graph data
- [x] Exporters auto-detect `shot_graph_vision.json` over classical
- [x] Motion-aware prompts and negative prompt injection per platform
- [x] Shared `common.resolve_shot_graph()` helper

## M4: Demo Lab Real Bridge ✅
- [x] `lab_server.py` — stdlib HTTP server with REST API
- [x] Endpoints: `/api/analyze`, `/api/panels`, `/api/extract-text`, `/api/vision`, `/api/director`
- [x] CORS enabled for browser SPA integration
- [x] `lab-server` CLI command

## M5: Production Hardening ✅
- [x] `schemas.py` — Pydantic models for Shot, Scene, Panel, Character, etc.
- [x] `telemetry.py` — session cost tracking, cache hit/miss logging, stage timings
- [x] `config.yaml` — quality presets, exporter settings, lab & telemetry config
- [x] Comprehensive test coverage for all new modules

## M6: CineForge Bridge ✅
- [x] `cineforge_export.py` — validate shot graph, file export, optional HTTP push
- [x] `export-cineforge` CLI (`--push`, `--cineforge-url`, `--project-id`)
- [x] `tests/test_cineforge_export.py`
- [x] `docs/CINEFORGE_BRIDGE.md`

## M7: Demo Lab Gen 2 — Production trust ✅

**Reality check:** M4/M5 shipped APIs and tests; Gen 2 (June 2026) made the browser lab operator-trustworthy. See `docs/DEMO_LAB_GEN2.md`.

| ID | Deliverable | Status |
|----|-------------|--------|
| G2.1 | `/health` capability probes (`lab_capabilities.py`) | ✅ |
| G2.2 | Unified `POST /api/pipeline/run` | ✅ |
| G2.3 | `pip install -e ".[lab]"` + `preflight-demo-lab.ps1` | ✅ |
| G2.4 | Scene graph OCR path fix; no client OCR overwrite | ✅ |
| G2.5 | Bubble + panel canvas overlays | ✅ |
| G2.6 | Playwright pipeline E2E gate | ✅ |
| G2.7 | Vision interpret hardening | ✅ |
| G2.8 | Multi-panel fixture regression | ✅ |
| G2.9 | Ops hardening (single-server guard, operator README) | ✅ |
| G2.10 | Beta exit (`install-demo-lab-fresh.ps1`, QA checklist) | ✅ |

**Done when:** Fresh install passes preflight, 4-panel comic QA checklist green, Playwright pipeline test in CI — **met**.
