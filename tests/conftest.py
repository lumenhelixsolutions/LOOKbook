"""pytest configuration for lookBOOK tests."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

# Detect Tesseract on Windows and configure pytesseract
_tesseract_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

for _p in _tesseract_paths:
    if Path(_p).exists():
        os.environ.setdefault("TESSERACT_CMD", _p)
        try:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = _p
        except ImportError:
            pass
        break


# ---------------------------------------------------------------------------
# Windows temp-directory permissions
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _ensure_windows_temp() -> None:
    """Ensure the custom pytest basetemp exists with writable permissions on Windows."""
    if sys.platform == "win32":
        base = Path("D:/tmp/pytest")
        base.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Provide a temporary project directory that is explicitly cleaned up after the test."""
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    yield project_dir
    if project_dir.exists():
        shutil.rmtree(project_dir, ignore_errors=True)
