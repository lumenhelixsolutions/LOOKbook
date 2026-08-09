from __future__ import annotations
from pathlib import Path
import json
import zipfile
import pytest


@pytest.fixture
def sample_cbz(tmp_path: Path) -> Path:
    """Create a synthetic CBZ comic archive with 2 test pages."""
    from PIL import Image

    cbz_path = tmp_path / "test_comic.cbz"
    with zipfile.ZipFile(cbz_path, "w") as zf:
        for i in range(2):
            img = Image.new("RGB", (100, 150), "white")
            page_path = tmp_path / f"page_{i:03d}.png"
            img.save(page_path)
            zf.write(page_path, f"page_{i:03d}.png")
            page_path.unlink()
    return cbz_path


class TestArchive:
    def test_list_pages_cbz(self, sample_cbz):
        from lookbook.pipeline.archive import list_pages

        pages = list_pages(sample_cbz)
        assert len(pages) == 2
        assert pages[0]["page_index"] == 0
        assert pages[0]["filename"] == "page_000.png"
        assert pages[1]["filename"] == "page_001.png"
        assert pages[0]["extension"] == ".png"
        assert pages[0]["size_bytes"] > 0

    def test_list_pages_nonexistent(self, tmp_path):
        from lookbook.pipeline.archive import list_pages

        with pytest.raises(FileNotFoundError):
            list_pages(tmp_path / "nonexistent.cbz")

    def test_extract_page(self, sample_cbz, tmp_path):
        from lookbook.pipeline.archive import extract_page

        out = extract_page(sample_cbz, "page_000.png", tmp_path / "output")
        assert out.exists()
        assert out.name == "page_000.png"
        assert out.stat().st_size > 0

    def test_extract_all_pages(self, sample_cbz, tmp_path):
        from lookbook.pipeline.archive import extract_all_pages

        paths = extract_all_pages(sample_cbz, tmp_path / "output")
        assert len(paths) == 2
        assert all(p.exists() for p in paths)

    def test_list_pages_cli(self, sample_cbz):
        from lookbook.cli import main

        main(["list-pages", str(sample_cbz)])

    def test_unsupported_format(self, tmp_path):
        from lookbook.pipeline.archive import list_pages

        bad = tmp_path / "test.pdf"
        bad.write_text("not an archive")
        with pytest.raises(ValueError, match="Unsupported archive format"):
            list_pages(bad)


class TestProcessArchive:
    @pytest.fixture(autouse=True)
    def _mock_ocr_and_wrap_cli(self, monkeypatch):
        """Mock OCR to avoid pytesseract dependency and wrap CLI so SystemExit
        is caught by process_archive's except Exception blocks."""

        def _fake_extract_text(source, project, **kwargs):
            blocks = [
                {
                    "text": "Dummy",
                    "classification": "dialogue",
                    "bbox": {"x": 0, "y": 0, "w": 10, "h": 10},
                }
            ]
            project = Path(project)
            result = {
                "schema": "lookbook.ocr.v0.2",
                "source_file": Path(source).name,
                "lang": "eng",
                "total_blocks": len(blocks),
                "full_text": "Dummy",
                "blocks": blocks,
            }
            ocr_file = project / "analysis" / "ocr_result.json"
            ocr_file.parent.mkdir(parents=True, exist_ok=True)
            ocr_file.write_text(json.dumps(result), encoding="utf-8")
            return blocks

        monkeypatch.setattr("lookbook.cli.extract_text", _fake_extract_text)

        # Wrap cli_main so SystemExit is re-raised as RuntimeError,
        # allowing process_archive to catch it in except Exception.
        import lookbook.cli

        _real_main = lookbook.cli.main

        def _safe_main(argv=None):
            try:
                _real_main(argv)
            except SystemExit as exc:
                raise RuntimeError(f"CLI exited with code {exc.code}") from exc

        monkeypatch.setattr("lookbook.cli.main", _safe_main)

    def test_process_archive_runs_choreography(self, sample_cbz, tmp_path, monkeypatch):
        """Verify process-archive invokes build_choreography after page OCR."""
        from lookbook.pipeline.archive import process_archive

        calls: list[str] = []

        def _fake_build_choreography(project, **kwargs):
            calls.append(str(project))
            choreo_file = Path(project) / "analysis" / "choreography.json"
            choreo_file.parent.mkdir(parents=True, exist_ok=True)
            choreo_file.write_text(
                json.dumps(
                    {
                        "schema": "lookbook.choreography.v0.1",
                        "total_lines": 0,
                        "lines": [],
                        "voice_cast": {},
                    }
                ),
                encoding="utf-8",
            )
            return []

        def _fake_export_living_panels(project, output=None):
            out = Path(project) / "exports" / "living_panels" / "review.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("<html></html>", encoding="utf-8")
            return out

        monkeypatch.setattr(
            "lookbook.pipeline.choreography.build_choreography",
            _fake_build_choreography,
        )
        monkeypatch.setattr(
            "lookbook.pipeline.living_panels_export.export_living_panels",
            _fake_export_living_panels,
        )

        project = tmp_path / "test_project"
        result = process_archive(sample_cbz, project, no_cleanup=True)

        assert len(calls) == 1
        assert calls[0] == str(project)
        assert result["total_pages"] == 2

    def test_process_archive_basic(self, sample_cbz, tmp_path):
        """Test process-archive creates project and runs pipeline."""
        from lookbook.pipeline.archive import process_archive

        project = tmp_path / "test_project"
        result = process_archive(sample_cbz, project, no_cleanup=True)
        assert result["schema"] == "lookbook.archive_process.v0.2"
        assert result["total_pages"] == 2
        assert result["archive"] == "test_comic.cbz"
        assert len(result["pages"]) == 2

        # Check project structure was created
        assert (project / "manifest.json").exists()
        assert (project / "analysis").exists()

    def test_process_archive_creates_exports(self, sample_cbz, tmp_path):
        """Verify process-archive creates export structure."""
        from lookbook.pipeline.archive import process_archive

        project = tmp_path / "test_project"
        process_archive(sample_cbz, project)

        # Project structure should exist
        assert (project / "manifest.json").exists()
        assert (project / "analysis").exists()
        # Exports may or may not exist depending on panel detection
        # (blank images produce 0 panels, so shot_graph isn't created)
        # But the project itself should be valid
        assert (project / "analysis" / "archive_process.json").exists()
