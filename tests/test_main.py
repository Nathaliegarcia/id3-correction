from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TRCK

from id3_correction.__main__ import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_mp3(path: Path, title: str | None = None, track: str | None = None) -> Path:
    path.write_bytes(b"")
    if title is not None or track is not None:
        tags = ID3()
        if title is not None:
            tags.add(TIT2(encoding=3, text=title))
        if track is not None:
            tags.add(TRCK(encoding=3, text=track))
        tags.save(str(path))
    return path


def _run_main(*args: str, stdin_input: str = "") -> tuple[int, str, str]:
    """Run main() with given CLI args. Returns (exit_code, stdout, stderr)."""
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    with (
        patch("sys.argv", ["id3-correction"] + list(args)),
        patch("sys.stdout", captured_out),
        patch("sys.stderr", captured_err),
        patch("sys.stdin", io.StringIO(stdin_input)),
    ):
        try:
            code = main()
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
    return code, captured_out.getvalue(), captured_err.getvalue()


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

class TestArgValidation:
    def test_less_than_2_folders_exits_1(self, tmp_path):
        code, out, err = _run_main(str(tmp_path))
        assert code == 1
        assert "at least 2" in err.lower() or "2 folder" in err.lower()

    def test_nonexistent_folder_exits_1(self, tmp_path):
        f1 = tmp_path / "f1"
        f1.mkdir()
        code, out, err = _run_main(str(f1), "/nonexistent/path/xyz")
        assert code == 1
        assert "does not exist" in err

    def test_help_flag(self):
        code, out, err = _run_main("--help")
        # argparse exits with 0 and prints help
        assert "usage" in out.lower() or "usage" in err.lower()


# ---------------------------------------------------------------------------
# All in sync
# ---------------------------------------------------------------------------

class TestAllInSync:
    def test_nothing_to_do_message(self, tmp_path):
        f1 = tmp_path / "f1"
        f2 = tmp_path / "f2"
        f1.mkdir()
        f2.mkdir()
        _create_mp3(f1 / "song.mp3", title="River", track="5")
        _create_mp3(f2 / "song.mp3", title="River", track="5")

        code, out, err = _run_main(str(f1), str(f2))
        assert code == 0
        assert "Nothing to do" in out or "in sync" in out.lower()


# ---------------------------------------------------------------------------
# Full pipeline with corrections
# ---------------------------------------------------------------------------

class TestPipelineWithCorrections:
    def test_report_shows_corrections(self, tmp_path):
        f1 = tmp_path / "f1"
        f2 = tmp_path / "f2"
        f3 = tmp_path / "f3"
        for d in [f1, f2, f3]:
            d.mkdir()
        _create_mp3(f1 / "song.mp3", title="River", track="5")
        _create_mp3(f2 / "song.mp3", title="River", track="5")
        _create_mp3(f3 / "song.mp3", title=None, track="5")  # missing title

        # Decline to apply
        code, out, err = _run_main(str(f1), str(f2), str(f3), stdin_input="n\n")
        assert "=== SCAN SUMMARY ===" in out
        assert "=== CORRECTIONS" in out
        assert "River" in out

    def test_apply_flag_modifies_files(self, tmp_path):
        f1 = tmp_path / "f1"
        f2 = tmp_path / "f2"
        f3 = tmp_path / "f3"
        for d in [f1, f2, f3]:
            d.mkdir()
        _create_mp3(f1 / "song.mp3", title="River", track="5")
        _create_mp3(f2 / "song.mp3", title="River", track="5")
        _create_mp3(f3 / "song.mp3", title=None, track="5")

        code, out, err = _run_main(str(f1), str(f2), str(f3), "--apply")
        assert code == 0
        # Verify tag was written
        tags = ID3(str(f3 / "song.mp3"))
        assert str(tags["TIT2"]) == "River"
        assert "1 files modified" in out or "files modified" in out

    def test_verbose_shows_per_file_details(self, tmp_path):
        f1 = tmp_path / "f1"
        f2 = tmp_path / "f2"
        for d in [f1, f2]:
            d.mkdir()
        _create_mp3(f1 / "song.mp3", title="River", track="5")
        _create_mp3(f2 / "song.mp3", title="River", track="5")

        code, out, err = _run_main(str(f1), str(f2), "--verbose")
        assert "VERBOSE" in out or "identity=" in out


# ---------------------------------------------------------------------------
# Conflict scenario
# ---------------------------------------------------------------------------

class TestConflict:
    def test_conflict_exits_2(self, tmp_path):
        f1 = tmp_path / "f1"
        f2 = tmp_path / "f2"
        f1.mkdir()
        f2.mkdir()
        _create_mp3(f1 / "song.mp3", title="Mountain", track="3")
        _create_mp3(f2 / "song.mp3", title="The Mountain", track="3")

        # User enters 0 (skip) for conflict
        code, out, err = _run_main(str(f1), str(f2), stdin_input="0\n")
        assert code == 2
        assert "CONFLICT" in out
