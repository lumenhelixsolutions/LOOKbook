"""
lookBOOK ↔ MoneyPrinterTurbo bridge

Provides helpers to invoke MPT tasks with lookBOOK-specific defaults:
  - No voiceover / TTS
  - 15-second target duration
  - Lower concurrency
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

# Ensure MPT's app package is importable when running in-process
_MPT_ROOT = Path(__file__).resolve().parents[1] / "moneyprinter"
if str(_MPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_MPT_ROOT))


class MPTBridge:
    """Project-specific bridge for MoneyPrinterTurbo (lookBOOK defaults)."""

    DEFAULT_DURATION: int = 15

    def __init__(self, endpoint: str = "http://127.0.0.1:8080") -> None:
        self.endpoint = endpoint.rstrip("/")
        self.project_defaults: dict[str, Any] = {
            "video_concat_mode": "sequential",
            "video_language": "en",
            "voice_name": "",               # no voiceover
            "voice_rate": "1.0",
            "subtitle_enabled": False,      # no subtitles
            "bgm_type": "random",
            "video_source": "pexels",
            # Duration hint: MPT doesn't have a global duration knob;
            # the bridge passes it as custom_params for downstream use.
            "target_duration": self.DEFAULT_DURATION,
        }

    def start_task(
        self,
        video_subject: str,
        video_script: str = "",
        video_terms: list[str] | None = None,
        video_concat_mode: str = "sequential",
        video_language: str = "en",
        voice_name: str = "",
        subtitle_enabled: bool = False,
        bgm_type: str = "random",
        target_duration: int = 15,
        custom_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start a video generation task via the MPT REST API."""
        import requests

        payload = {
            "video_subject": video_subject,
            "video_script": video_script,
            "video_terms": video_terms or [],
            "video_concat_mode": video_concat_mode,
            "video_language": video_language,
            "voice_name": voice_name,
            "subtitle_enabled": subtitle_enabled,
            "bgm_type": bgm_type,
            "target_duration": target_duration,
        }
        if custom_params:
            payload.update(custom_params)

        resp = requests.post(f"{self.endpoint}/api/v1/videos", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Query task status and results."""
        import requests

        resp = requests.get(
            f"{self.endpoint}/api/v1/videos/{task_id}", timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def generate_direct(
        self,
        video_subject: str,
        video_script: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """In-process task kick-off (requires MPT app imports)."""
        from app.models.schema import VideoParams
        from app.services import task as tm
        from app.services import state as sm
        from app.models import const
        from app.utils import utils

        task_id = str(uuid.uuid4())
        merged = {**self.project_defaults, **kwargs}
        params = VideoParams(
            video_subject=video_subject,
            video_script=video_script,
            **merged,
        )

        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_PROCESSING,
            progress=0,
        )
        try:
            result = tm.start(task_id=task_id, params=params)
            return {"task_id": task_id, "status": "completed", "result": result}
        except Exception as exc:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            return {"task_id": task_id, "status": "failed", "error": str(exc)}


def get_bridge() -> MPTBridge:
    """Return a configured bridge instance."""
    endpoint = os.getenv("MPT_ENDPOINT", "http://127.0.0.1:8080")
    return MPTBridge(endpoint=endpoint)
