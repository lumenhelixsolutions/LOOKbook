from __future__ import annotations
from pathlib import Path
from typing import Any
import shutil
from ..models import write_json


_WINDOWS_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _configure_tesseract() -> None:
    """Point pytesseract at the Windows binary when it is not on PATH."""
    try:
        import pytesseract
    except ImportError:
        return
    if shutil.which("tesseract"):
        return
    for candidate in _WINDOWS_TESSERACT_PATHS:
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            break


def _tesseract_available() -> bool:
    """Check if Tesseract OCR engine is installed and in PATH."""
    _configure_tesseract()
    try:
        import pytesseract

        cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        return Path(cmd).exists() if "\\" in str(cmd) or "/" in str(cmd) else shutil.which("tesseract") is not None
    except ImportError:
        return False


def preprocess_image(path: Path, output_dir: Path | None = None) -> Path:
    """Preprocess a comic page image for better OCR accuracy.

    Applies: grayscale → contrast enhancement → threshold → deskew.
    Returns path to the preprocessed image.
    """
    from PIL import Image, ImageFilter, ImageOps

    img = Image.open(path).convert("L")  # grayscale
    # Enhance contrast
    img = ImageOps.autocontrast(img, cutoff=5)
    # Apply sharpening filter
    img = img.filter(ImageFilter.SHARPEN)
    # Binarize with adaptive-style threshold (simple fixed threshold works well after autocontrast)
    img = img.point(lambda x: 255 if x > 128 else 0, mode="1").convert("L")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{path.stem}_preprocessed{path.suffix}"
        img.save(out_path)
        return out_path
    return path


def extract_text(
    source: str | Path,
    project: str | Path,
    lang: str = "eng",
    psm: int = 6,
    preprocess: bool = True,
) -> list[dict[str, Any]]:
    """Extract text from a comic page image using Tesseract OCR.

    Returns a list of text blocks with bounding boxes and confidence scores.
    Each block: {text, conf, bbox: {x, y, w, h}, block_num, line_num}
    """
    if not _tesseract_available():
        raise RuntimeError(
            "Tesseract OCR unavailable — install pytesseract (pip install pytesseract) "
            "and the Tesseract engine (choco install tesseract)."
        )

    import pytesseract

    _configure_tesseract()
    source = Path(source)
    project = Path(project)

    if not source.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    img_path = source
    if preprocess:
        preproc_dir = project / ".cache" / "preprocessed"
        img_path = preprocess_image(source, preproc_dir)

    # Run Tesseract with detailed output
    custom_config = f"--psm {psm} -l {lang} --oem 1"
    data = pytesseract.image_to_data(
        str(img_path),
        config=custom_config,
        output_type=pytesseract.Output.DICT,
    )

    blocks: list[dict[str, Any]] = []
    seen_blocks: set[int] = set()

    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
        block_num = int(data["block_num"][i])
        if not text or conf < 10:
            continue
        # Deduplicate by block number — consolidate into full block text
        if block_num not in seen_blocks:
            seen_blocks.add(block_num)
            blocks.append(
                {
                    "text": text,
                    "conf": conf,
                    "bbox": {
                        "x": int(data["left"][i]),
                        "y": int(data["top"][i]),
                        "w": int(data["width"][i]),
                        "h": int(data["height"][i]),
                    },
                    "block_num": block_num,
                    "line_num": int(data["line_num"][i]),
                    "paragraph_num": int(data.get("para_num", [0])[i])
                    if len(data.get("para_num", [])) > i
                    else 0,
                }
            )
        else:
            # Append to existing block text
            for b in blocks:
                if b["block_num"] == block_num:
                    b["text"] += " " + text
                    # Expand bbox to encompass
                    bx = b["bbox"]
                    rx = int(data["left"][i])
                    ry = int(data["top"][i])
                    rw = int(data["width"][i])
                    rh = int(data["height"][i])
                    bx["x"] = min(bx["x"], rx)
                    bx["y"] = min(bx["y"], ry)
                    bx["w"] = max(bx["w"], rx + rw - bx["x"])
                    bx["h"] = max(bx["h"], ry + rh - bx["y"])
                    break

    # Classification hint: try to identify dialogue vs narration vs SFX
    for b in blocks:
        b["classification"] = _classify_text_block(b)

    result = {
        "schema": "lookbook.ocr.v0.2",
        "source_file": source.name,
        "lang": lang,
        "total_blocks": len(blocks),
        "full_text": " ".join(b["text"] for b in blocks),
        "blocks": blocks,
    }

    analysis_dir = project / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    write_json(analysis_dir / "ocr_result.json", result)

    return blocks


def _classify_text_block(block: dict[str, Any]) -> str:
    """Classify a text block as dialogue, narration, SFX, or caption."""
    text = block["text"].strip()
    # Dialogue: quoted text
    if text.startswith(('"', '"', "'", "'", "\u201c", "\u300c")) or text.endswith(
        ('"', '"', "'", "'", "\u201d", "\u300d")
    ):
        return "dialogue"
    # SFX: all caps and short
    if text.isupper() and len(text.split()) <= 4:
        return "sfx"
    # Narration: starts with typical narration markers
    if any(
        text.startswith(m) for m in ["NARRATOR:", "Once upon", "Meanwhile", "Later", "Suddenly"]
    ):
        return "narration"
    return "caption"
