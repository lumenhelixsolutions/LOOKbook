"""Demo Lab capability probes — honest reporting for /health and preflight."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

from .config import get_api_key, get_config
from .pipeline.ocr import _tesseract_available


def get_lab_capabilities() -> dict:
    """Return what the local lab can actually do (no mocked claims)."""
    notes: list[str] = []
    pillow = importlib.util.find_spec("PIL") is not None
    opencv = importlib.util.find_spec("cv2") is not None
    pytesseract = importlib.util.find_spec("pytesseract") is not None
    ocr = _tesseract_available()
    panels = pillow and opencv

    provider = get_config()["vision"]["provider"]
    vision_llm = bool(get_api_key(provider))

    if not pillow:
        notes.append("Install Pillow: pip install lookbook-ai[lab]")
    if not opencv:
        notes.append("Install OpenCV: pip install lookbook-ai[lab]")
    if not pytesseract:
        notes.append("Install pytesseract: pip install lookbook-ai[lab]")
    if not ocr:
        notes.append("Tesseract binary missing — choco install tesseract (Windows)")
    if not vision_llm:
        notes.append(f"Vision LLM off — set API key for {provider}")

    ready = panels and ocr

    return {
        "panels": panels,
        "ocr": ocr,
        "opencv": opencv,
        "pillow": pillow,
        "pytesseract": pytesseract,
        "vision_llm": vision_llm,
        "vision_provider": provider,
        "ready_for_pipeline": ready,
        "notes": notes,
    }