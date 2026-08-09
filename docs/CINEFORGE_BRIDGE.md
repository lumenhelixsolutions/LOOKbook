# lookBOOK → CineForge Bridge

Hand off a validated `shot_graph` from lookBOOK into [CineForge](https://github.com/lumenhelixsolutions/cineforge) storyboard shots.

## Prerequisites

1. A lookBOOK project with `analysis/shot_graph.json` or `analysis/shot_graph_vision.json`
2. For live push: CineForge backend running (default `http://127.0.0.1:8000`) and an existing project UUID

## Quick path

```bash
# Build shot graph (classical or vision)
lookbook build-shot-graph my-demo
# lookbook build-shot-graph my-demo --use-vision --vision-provider gemini

# Export ingest-ready JSON (default)
lookbook export-cineforge my-demo

# Push directly into CineForge
lookbook export-cineforge my-demo \
  --push \
  --cineforge-url http://127.0.0.1:8000 \
  --project-id <cineforge-project-uuid>
```

## Output artifact

Default path: `my-demo/exports/cineforge/ingest.json`

```json
{
  "schema": "lookbook.cineforge_export.v1",
  "shot_graph": { "schema": "lookbook.shot_graph.v0.3", "shots": [] },
  "replace_existing_shots": true,
  "source_project": "D:/path/to/my-demo",
  "shot_graph_path": "analysis/shot_graph_vision.json"
}
```

## CineForge API

Manual ingest (same payload as `--push`):

```http
POST /projects/{project_id}/ingest/lookbook
Content-Type: application/json

{
  "shot_graph": { "schema": "lookbook.shot_graph.v0.3", "shots": [] },
  "replace_existing_shots": true
}
```

See CineForge [`docs/API.md`](../../cineforge/docs/API.md) for response fields (`shot_count`, `treatment_id`).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `CINEFORGE_URL` | API base when `--cineforge-url` omitted |
| `CINEFORGE_API_KEY` | Optional `X-API-Key` when auth is enabled |

## Field mapping

CineForge maps each lookBOOK shot to storyboard records (prompt text, duration snap to 4/6/8s, continuity, transitions). Mapping logic lives in `cineforge/backend/ingest/lookbook.py` — lookBOOK does not depend on that package at runtime.

## Troubleshooting

| Error | Fix |
|-------|-----|
| Shot graph not found | Run `build-shot-graph` first |
| at least one shot | Ensure analysis JSON has non-empty `shots` |
| 404 on push | Verify `--project-id` exists in CineForge |
| Connection refused | Start CineForge backend; check `CINEFORGE_URL` |