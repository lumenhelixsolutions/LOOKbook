# API

## Python API

```python
from lookbook.project import init_project
from lookbook.pipeline.analyze import analyze_source
from lookbook.pipeline.true_animation_packet import create_true_animation_packet
from lookbook.pipeline.export_web import export_web
from lookbook.video.animatic import build_animatic, generate_shot_clip, shot_to_mpt_prompt
```

## HTTP Endpoints (Lab Server)

The demo lab server (`lookbook.lab_server`) exposes a lightweight stdlib-based HTTP API:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analyze` | Run full pipeline on uploaded image |
| `POST` | `/api/extract-text` | OCR on uploaded image |
| `POST` | `/api/panels` | Panel detection |
| `GET`  | `/api/project/{id}` | Read project analysis JSONs |
| `GET`  | `/api/export/{id}` | List export artifacts |
| `POST` | `/api/vision` | Run vision LLM on uploaded image |
| `POST` | `/api/director` | Generate director decisions for a target platform |
| `POST` | `/api/animatic` | Generate animatic MP4 from shot JSON |
| `GET`  | `/api/animatic/{id}` | Download generated animatic MP4 |

### Animatic Endpoints

#### `POST /api/animatic`

Generate a low-fidelity animatic MP4 from a shot graph.

**JSON body**
```json
{
  "shot_graph": {
    "schema": "lookbook.shot_graph.v0.3",
    "total_shots": 2,
    "shots": [
      {
        "shot_index": 0,
        "type": "establishing",
        "camera": "pan right",
        "motion_directive": "Slow pan across the scene.",
        "dialogue": [],
        "narration": ["The scene opens on a vast landscape."],
        "characters": []
      }
    ]
  }
}
```

**Response**
```json
{
  "project_id": "a1b2c3d4",
  "animatic_path": ".../animatic.mp4",
  "preview_url": "/api/animatic/a1b2c3d4",
  "total_shots": 2,
  "total_duration_seconds": 6.0
}
```

#### `GET /api/animatic/{project_id}`

Download the generated animatic MP4. Returns `200` with `Content-Type: video/mp4`, or `404` if the project or animatic does not exist.
