"""Tests for CLI error handling, exit codes, and help text."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from lookbook.cli import build_parser, main


class TestCLIErrors:
    def test_exit_2_on_invalid_args(self):
        """Unknown sub-command should exit with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent-command"])
        assert exc_info.value.code == 2

    def test_exit_3_on_missing_project(self, tmp_path: Path):
        """Missing project / file should exit with code 3."""
        missing_project = tmp_path / "does_not_exist"
        with pytest.raises(SystemExit) as exc_info:
            main(["export-runway", str(missing_project)])
        assert exc_info.value.code == 3

    def test_verbose_shows_traceback(self, tmp_path: Path, capsys):
        """With --verbose, a traceback should be printed to stderr."""
        missing_project = tmp_path / "does_not_exist"
        with pytest.raises(SystemExit) as exc_info:
            main(["-v", "export-runway", str(missing_project)])
        assert exc_info.value.code == 3
        captured = capsys.readouterr()
        assert "Traceback" in captured.err

    def test_main_help_is_comprehensive(self):
        """Top-level --help should mention the program, description, and --verbose flag."""
        parser = build_parser()
        help_text = parser.format_help()
        assert "lookbook" in help_text.lower()
        assert "--verbose" in help_text
        assert "Available commands" in help_text or "commands:" in help_text.lower()

    def test_subcommand_help_is_comprehensive(self):
        """Every sub-command should have a non-empty help description."""
        import argparse
        parser = build_parser()
        subparser_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparser_action = action
                break
        assert subparser_action is not None
        for name, sub in subparser_action.choices.items():
            assert sub.description or sub.prog, f"Sub-command {name} lacks help text"

    def test_exit_4_on_permission_denied(self, tmp_path: Path, monkeypatch):
        """PermissionError should exit with code 4."""

        def _raise_perm(*args, **kwargs):
            raise PermissionError("Access denied")

        monkeypatch.setattr("lookbook.cli.shutil.copy2", _raise_perm)
        with pytest.raises(SystemExit) as exc_info:
            main(["analyze-source", str(tmp_path / "src.png"), str(tmp_path / "proj")])
        assert exc_info.value.code == 4

    def test_exit_1_on_generic_error(self, tmp_path: Path, monkeypatch):
        """Unhandled exceptions should exit with code 1."""
        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("lookbook.cli.export_runway", _boom)
        with pytest.raises(SystemExit) as exc_info:
            main(["export-runway", str(tmp_path)])
        assert exc_info.value.code == 1

    def test_subcommand_help_invocations(self):
        """Every sub-command should respond to --help with exit code 0."""
        import argparse

        parser = build_parser()
        subparser_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparser_action = action
                break
        assert subparser_action is not None
        for name in subparser_action.choices:
            with pytest.raises(SystemExit) as exc_info:
                main([name, "--help"])
            assert exc_info.value.code == 0, f"Sub-command {name} --help did not exit cleanly"
