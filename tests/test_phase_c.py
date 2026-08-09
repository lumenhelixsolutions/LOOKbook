from __future__ import annotations
from pathlib import Path
import importlib.util
import json
import shutil

import pytest

_tesseract_available = (
    importlib.util.find_spec("pytesseract") is not None
    and shutil.which("tesseract") is not None
)

# ---- Fixtures ----


@pytest.fixture
def test_project(tmp_path: Path) -> Path:
    """Create a minimal lookBOOK project with sample assets."""
    project = tmp_path / "test_project"
    project.mkdir(parents=True)
    (project / "source").mkdir()
    (project / "analysis").mkdir()
    (project / "prompts").mkdir()
    (project / "exports").mkdir()
    manifest = {
        "project": "Test Project",
        "format_version": "0.2",
        "source_type": "image",
        "rights_mode": "test",
        "output_intent": "true_image_to_video_animation",
    }
    (project / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return project


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a synthetic comic-style image with known features."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        pytest.skip("Pillow not available")

    img = Image.new("RGB", (400, 600), "white")
    draw = ImageDraw.Draw(img)

    # Draw panel borders simulating a 2x2 grid
    # Panel 1 (top-left)
    draw.rectangle([5, 5, 195, 295], outline="black", width=3)
    draw.text((30, 120), "Hello world", fill="black")
    # Panel 2 (top-right)
    draw.rectangle([205, 5, 395, 295], outline="black", width=3)
    draw.text((230, 120), '"Dialogue text"', fill="black")
    # Panel 3 (bottom-left)
    draw.rectangle([5, 305, 195, 595], outline="black", width=3)
    draw.text((30, 420), "NARRATOR: Once upon a time", fill="black")
    # Panel 4 (bottom-right)
    draw.rectangle([205, 305, 395, 595], outline="black", width=3)
    draw.text((230, 420), "BOOM", fill="black")

    path = tmp_path / "test_comic.png"
    img.save(path)
    return path


# ---- OCR Tests ----


class TestOCR:
    def test_classify_text_block(self):
        from lookbook.pipeline.ocr import _classify_text_block

        assert _classify_text_block({"text": '"Hello there"'}) == "dialogue"
        assert _classify_text_block({"text": "NARRATOR: Once upon a time"}) == "narration"
        assert _classify_text_block({"text": "BOOM"}) == "sfx"
        assert _classify_text_block({"text": "Some caption text"}) == "caption"

    def test_preprocess_image(self, sample_image, tmp_path):
        from lookbook.pipeline.ocr import preprocess_image

        out = preprocess_image(sample_image, tmp_path / "preproc")
        assert out.exists()
        from PIL import Image

        img = Image.open(out)
        assert img.mode == "L"  # grayscale

    @pytest.mark.skipif(not _tesseract_available, reason="tesseract not installed")
    def test_extract_text_integration(self, sample_image, test_project):
        """End-to-end: extract text from a synthetic comic page."""
        from lookbook.pipeline.ocr import extract_text

        blocks = extract_text(sample_image, test_project)
        assert isinstance(blocks, list)
        if blocks:  # Tesseract may find text on the synthetic image
            assert all("text" in b for b in blocks)
            assert all("bbox" in b for b in blocks)
            # Check output file was written
            result_file = test_project / "analysis" / "ocr_result.json"
            assert result_file.exists()
            data = json.loads(result_file.read_text())
            assert data["schema"] == "lookbook.ocr.v0.2"
            assert "full_text" in data


# ---- Panel Detection Tests ----


class TestPanels:
    def test_detect_panels_integration(self, sample_image, test_project):
        """Detect panels from synthetic comic page."""
        import importlib.util

        if importlib.util.find_spec("cv2") is None:
            pytest.skip("OpenCV not available")

        from lookbook.pipeline.panels import detect_panels

        panels = detect_panels(sample_image, test_project)
        assert isinstance(panels, list)
        # Our synthetic image has 4 visible panel regions
        # (contour detection may find more due to noise)
        assert len(panels) >= 2, f"Expected at least 2 panels, got {len(panels)}"
        for p in panels:
            assert "panel_index" in p
            assert "bbox" in p
            bx = p["bbox"]
            for k in ("x", "y", "w", "h"):
                assert k in bx

        # Check output file
        result_file = test_project / "analysis" / "panel_analysis.json"
        assert result_file.exists()
        data = json.loads(result_file.read_text())
        assert data["schema"] == "lookbook.panels.v0.2"
        assert data["total_panels"] == len(panels)


# ---- Character Extraction Tests ----


class TestCharacters:
    def test_average_hash(self, sample_image):
        from lookbook.pipeline.characters import _average_hash

        h = _average_hash(sample_image)
        assert isinstance(h, str)
        assert len(h) == 16  # 8x8 hash = 64 bits = 16 hex chars

    def test_hamming_distance(self):
        from lookbook.pipeline.characters import _hamming_distance

        assert _hamming_distance("0" * 16, "0" * 16) == 0.0
        assert _hamming_distance("f" * 16, "0" * 16) > 0.0

    def test_extract_characters_needs_panels(self, sample_image, test_project):
        """Should fail gracefully if panel analysis doesn't exist."""
        from lookbook.pipeline.characters import extract_characters

        with pytest.raises(FileNotFoundError):
            extract_characters(sample_image, test_project)


# ---- Scene Graph Tests ----


class TestSceneGraph:
    def test_build_scene_graph_needs_panels(self, test_project):
        """Should fail gracefully if no panel data."""
        from lookbook.pipeline.scene_graph import build_scene_graph

        with pytest.raises(ValueError, match="No panel data found"):
            build_scene_graph(test_project)

    def test_scene_graph_with_mock_data(self, test_project):
        """Test scene graph logic with pre-created panel data."""
        from lookbook.pipeline.scene_graph import build_scene_graph

        # Create mock panel analysis
        mock_panels = {
            "panels": [
                {"panel_index": 0, "bbox": {"x": 0, "y": 0, "w": 100, "h": 100}, "area": 10000},
                {"panel_index": 1, "bbox": {"x": 100, "y": 0, "w": 100, "h": 100}, "area": 10000},
                {"panel_index": 2, "bbox": {"x": 0, "y": 100, "w": 100, "h": 100}, "area": 10000},
            ]
        }
        pfile = test_project / "analysis" / "panel_analysis.json"
        pfile.write_text(json.dumps(mock_panels))

        scenes = build_scene_graph(test_project)
        assert isinstance(scenes, list)
        assert len(scenes) >= 1
        assert scenes[0]["scene_index"] == 0
        assert scenes[0]["panel_count"] > 0


# ---- Shot Graph Tests ----


class TestShotGraph:
    def test_build_shot_graph_needs_scenes(self, test_project):
        """Should fail gracefully if no scene graph."""
        from lookbook.pipeline.shot_graph import build_shot_graph

        with pytest.raises(FileNotFoundError):
            build_shot_graph(test_project)

    def test_shot_graph_with_mock_scenes(self, test_project):
        """Test shot graph generation from mock scene data."""
        from lookbook.pipeline.shot_graph import build_shot_graph

        mock_scenes = {
            "schema": "lookbook.scene_graph.v0.2",
            "source_file": "test.png",
            "total_scenes": 2,
            "scenes": [
                {
                    "scene_index": 0,
                    "panel_count": 2,
                    "panel_indices": [0, 1],
                    "panels": [
                        {"panel_index": 0, "bbox": {"x": 0, "y": 0, "w": 100, "h": 100}},
                        {"panel_index": 1, "bbox": {"x": 100, "y": 0, "w": 100, "h": 100}},
                    ],
                    "characters": ["char_000"],
                    "dialogue": ['"Hello world"'],
                    "narration": [],
                },
                {
                    "scene_index": 1,
                    "panel_count": 1,
                    "panel_indices": [2],
                    "panels": [{"panel_index": 2, "bbox": {"x": 0, "y": 100, "w": 100, "h": 100}}],
                    "characters": [],
                    "dialogue": [],
                    "narration": ["The end."],
                },
            ],
        }
        sfile = test_project / "analysis" / "scene_graph.json"
        sfile.write_text(json.dumps(mock_scenes))

        shots = build_shot_graph(test_project)
        assert isinstance(shots, list)
        assert len(shots) >= 2  # At least 2 shots for 2 scenes
        assert all("shot_index" in s for s in shots)
        assert all("duration_seconds" in s for s in shots)
        assert all("camera" in s for s in shots)

        # Check output file
        result_file = test_project / "analysis" / "shot_graph.json"
        assert result_file.exists()
        data = json.loads(result_file.read_text())
        assert data["schema"] == "lookbook.shot_graph.v0.2"
        assert data["total_shots"] == len(shots)


# ---- CLI Smoke Tests ----


class TestCLIIntegration:
    @pytest.mark.skipif(not _tesseract_available, reason="tesseract not installed")
    def test_extract_text_cli(self, sample_image, test_project):
        """Verify extract-text CLI command produces correct output."""
        from lookbook.cli import main

        main(["extract-text", str(sample_image), str(test_project)])
        result_file = test_project / "analysis" / "ocr_result.json"
        assert result_file.exists()

    def test_detect_panels_cli(self, sample_image, test_project):
        """Verify detect-panels CLI command."""
        import importlib.util

        if importlib.util.find_spec("cv2") is None:
            pytest.skip("OpenCV not available")

        from lookbook.cli import main

        main(["detect-panels", str(sample_image), str(test_project)])
        result_file = test_project / "analysis" / "panel_analysis.json"
        assert result_file.exists()

    def test_build_scene_graph_cli(self, test_project):
        """Verify build-scene-graph CLI with mock data."""
        from lookbook.cli import main

        # Inject mock panel data
        mock_panels = {
            "panels": [
                {"panel_index": 0, "bbox": {"x": 0, "y": 0, "w": 100, "h": 100}, "area": 10000},
                {"panel_index": 1, "bbox": {"x": 100, "y": 0, "w": 100, "h": 100}, "area": 10000},
            ]
        }
        (test_project / "analysis" / "panel_analysis.json").write_text(json.dumps(mock_panels))

        main(["build-scene-graph", str(test_project)])
        assert (test_project / "analysis" / "scene_graph.json").exists()

    def test_build_shot_graph_cli(self, test_project):
        """Verify build-shot-graph CLI with mock data."""
        from lookbook.cli import main

        mock_scenes = {
            "schema": "lookbook.scene_graph.v0.2",
            "scenes": [
                {
                    "scene_index": 0,
                    "panel_count": 1,
                    "panel_indices": [0],
                    "panels": [{"panel_index": 0, "bbox": {"x": 0, "y": 0, "w": 100, "h": 100}}],
                    "characters": [],
                    "dialogue": [],
                    "narration": [],
                }
            ],
        }
        (test_project / "analysis" / "scene_graph.json").write_text(json.dumps(mock_scenes))

        main(["build-shot-graph", str(test_project)])
        assert (test_project / "analysis" / "shot_graph.json").exists()
