# lookBOOK — Agent context

Canonical repo: `D:\projects\lookBOOK`

## Demo Lab (Gen 2)

| Item | Path / command |
|------|----------------|
| Server | `python -m lookbook.lab_server` → http://localhost:8042 |
| **Ant Design UI** | `demo-lab-react/` → http://localhost:8042/react/ after `npm run build` |
| UI skill | `D:\projects\skills\ant-design\SKILL.md` |
| Start script | `scripts/start-demo-lab.ps1` (kills stale :8042; runs preflight first) |
| Fresh install | `scripts/install-demo-lab-fresh.ps1` |
| Preflight | `scripts/preflight-demo-lab.ps1` |
| Vault handoff | `POST /api/import-vault` · `scripts/pipeline-research-story.ps1` (portfolio) |
| Director graph | `scripts/start-director-graph.ps1` → `:7791` · `POST /api/director-graph/run` · `lookbook director-graph-run` |
| Install deps | `pip install -e ".[lab]"` + Tesseract on PATH |
| Plan | `docs/DEMO_LAB_GEN2.md` |
| API v5 | `POST /api/pipeline/run` — unified panels → OCR → interpret |

## Health

`GET /health` returns `version: 5` and `capabilities` (panels, ocr, vision_llm, ready_for_pipeline).

## Tests

```powershell
python scripts/generate_comic_fixture.py   # tests/fixtures/comic_2x2.png (4-panel)
python -m pytest tests/ -q
npx playwright test tests/e2e/demo-lab.spec.mjs
```

CI job `lab-e2e` in `.github/workflows/ci.yml` runs pytest + Playwright on `:8042`.

## Session plan (Wave 1)

`docs/PIPELINE_SESSION_PLAN_20.md` — **S1–S7** ✅. Next: **S8** research→story portfolio E2E harness.

## Milestones

See `MILESTONES.md` — M7 Demo Lab Gen 2 **done**.