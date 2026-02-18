"""End-to-end tests covering 8 realistic scenarios from PLAN.md Step 9."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TRCK

from id3_correction.__main__ import main
from id3_correction.analyzer import analyze
from id3_correction.reporter import generate_report
from id3_correction.scanner import scan_folders


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _create_mp3(path: Path, title: str | None = None, track: str | None = None) -> Path:
    """Create a minimal MP3 file with optional ID3 tags."""
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _read_title(path: Path) -> str | None:
    try:
        tags = ID3(str(path))
        return str(tags["TIT2"]) if "TIT2" in tags else None
    except ID3NoHeaderError:
        return None


def _read_track(path: Path) -> int | None:
    try:
        tags = ID3(str(path))
        if "TRCK" not in tags:
            return None
        val = str(tags["TRCK"]).split("/")[0].strip()
        return int(val) if val else None
    except ID3NoHeaderError:
        return None


# ---------------------------------------------------------------------------
# Scenario A — clean sync: identical files and tags
# ---------------------------------------------------------------------------

class TestScenarioA:
    def test_clean_sync_nothing_to_do(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()
        for d in [f1, f2, f3]:
            _create_mp3(d / "01 - River.mp3", title="River", track="1")
            _create_mp3(d / "02 - Mountain.mp3", title="Mountain", track="2")

        code, out, err = _run_main(str(f1), str(f2), str(f3))
        assert code == 0
        assert "Nothing to do" in out or "in sync" in out.lower()
        assert "=== CORRECTIONS" not in out
        assert "=== CONFLICTS" not in out


# ---------------------------------------------------------------------------
# Scenario B — missing title in one folder
# ---------------------------------------------------------------------------

class TestScenarioB:
    def test_missing_title_correction_proposed(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()
        _create_mp3(f1 / "song.mp3", title="River", track="5")
        _create_mp3(f2 / "song.mp3", title="River", track="5")
        _create_mp3(f3 / "song.mp3", title=None, track="5")

        # Decline to apply
        code, out, err = _run_main(str(f1), str(f2), str(f3), stdin_input="n\n")
        assert "=== CORRECTIONS" in out
        assert "River" in out
        assert str(f3 / "song.mp3") in out

    def test_missing_title_applied_correctly(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()
        _create_mp3(f1 / "song.mp3", title="River", track="5")
        _create_mp3(f2 / "song.mp3", title="River", track="5")
        _create_mp3(f3 / "song.mp3", title=None, track="5")

        code, out, err = _run_main(str(f1), str(f2), str(f3), "--apply")
        assert code == 0
        assert _read_title(f3 / "song.mp3") == "River"


# ---------------------------------------------------------------------------
# Scenario C — missing track, filename fallback
# ---------------------------------------------------------------------------

class TestScenarioC:
    def test_filename_fallback_proposed(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()
        for d in [f1, f2, f3]:
            _create_mp3(d / "05 - River.mp3", title="River", track=None)

        # Decline individual prompt
        code, out, err = _run_main(str(f1), str(f2), str(f3), stdin_input="n\nn\nn\n")
        # Should propose corrections from filename fallback
        assert "=== CORRECTIONS" in out
        assert "filename" in out
        assert "requires confirmation" in out

    def test_filename_fallback_applied(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()
        for d in [f1, f2, f3]:
            _create_mp3(d / "05 - River.mp3", title="River", track=None)

        # Accept all 3 individual prompts
        code, out, err = _run_main(str(f1), str(f2), str(f3), stdin_input="y\ny\ny\n")
        assert code == 0
        for d in [f1, f2, f3]:
            assert _read_track(d / "05 - River.mp3") == 5


# ---------------------------------------------------------------------------
# Scenario D — missing track, title-match fallback
# ---------------------------------------------------------------------------

class TestScenarioD:
    def test_title_match_fallback_proposed(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()
        # "River.mp3" has title "River" but no track (no leading number in filename)
        for d in [f1, f2, f3]:
            _create_mp3(d / "River.mp3", title="River", track=None)
        # "05 - River.mp3" has title "River" and track 5
        for d in [f1, f2, f3]:
            _create_mp3(d / "05 - River.mp3", title="River", track="5")

        code, out, err = _run_main(str(f1), str(f2), str(f3), stdin_input="n\nn\nn\n")
        # "River.mp3" group should get title_match fallback
        assert "title_match" in out
        assert "requires confirmation" in out

    def test_title_match_fallback_applied(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()
        for d in [f1, f2, f3]:
            _create_mp3(d / "River.mp3", title="River", track=None)
        for d in [f1, f2, f3]:
            _create_mp3(d / "05 - River.mp3", title="River", track="5")

        # Accept all individual prompts (3 for "River.mp3" group)
        code, out, err = _run_main(str(f1), str(f2), str(f3), stdin_input="y\ny\ny\n")
        assert code == 0
        for d in [f1, f2, f3]:
            assert _read_track(d / "River.mp3") == 5


# ---------------------------------------------------------------------------
# Scenario E — conflict: 2 vs 2 folders
# ---------------------------------------------------------------------------

class TestScenarioE:
    def test_conflict_reported(self, tmp_path):
        f1, f2, f3, f4 = (tmp_path / f"f{i}" for i in range(1, 5))
        for d in [f1, f2, f3, f4]:
            d.mkdir()
        _create_mp3(f1 / "song.mp3", title="Mountain", track="3")
        _create_mp3(f2 / "song.mp3", title="Mountain", track="3")
        _create_mp3(f3 / "song.mp3", title="The Mountain", track="3")
        _create_mp3(f4 / "song.mp3", title="The Mountain", track="3")

        code, out, err = _run_main(str(f1), str(f2), str(f3), str(f4), stdin_input="0\n")
        assert "=== CONFLICTS" in out
        assert "Mountain" in out
        assert "The Mountain" in out
        assert "No strict majority" in out
        assert code == 2  # unresolved conflicts


# ---------------------------------------------------------------------------
# Scenario F — missing file in one folder
# ---------------------------------------------------------------------------

class TestScenarioF:
    def test_missing_file_flagged(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()
        _create_mp3(f1 / "song.mp3", title="River", track="5")
        _create_mp3(f2 / "song.mp3", title="River", track="5")
        # f3 does not have song.mp3 but has another file
        _create_mp3(f3 / "other.mp3", title="Other", track="1")
        # Also add song.mp3 to f1 and f2's other.mp3 to f1 and f2 so f3 isn't missing all
        _create_mp3(f1 / "other.mp3", title="Other", track="1")
        _create_mp3(f2 / "other.mp3", title="Other", track="1")

        code, out, err = _run_main(str(f1), str(f2), str(f3), stdin_input="n\n")
        assert "=== MISSING FILES ===" in out
        assert "song" in out
        # f3 should be mentioned as missing
        assert str(f3) in out or f3.name in out


# ---------------------------------------------------------------------------
# Scenario G — non-MP3 file: warning emitted
# ---------------------------------------------------------------------------

class TestScenarioG:
    def test_non_mp3_warning(self, tmp_path):
        f1, f2 = (tmp_path / f"f{i}" for i in range(1, 3))
        for d in [f1, f2]:
            d.mkdir()
        _create_mp3(f1 / "song.mp3", title="River", track="5")
        _create_mp3(f2 / "song.mp3", title="River", track="5")
        # Add a non-MP3 file to f1
        (f1 / "cover.flac").write_bytes(b"")

        code, out, err = _run_main(str(f1), str(f2))
        assert "=== WARNINGS ===" in out
        assert "cover.flac" in out
        assert "non-MP3" in out


# ---------------------------------------------------------------------------
# Scenario H — full apply: verify actual file modification
# ---------------------------------------------------------------------------

class TestScenarioH:
    def test_full_apply_with_multiple_corrections(self, tmp_path):
        f1, f2, f3 = (tmp_path / f"f{i}" for i in range(1, 4))
        for d in [f1, f2, f3]:
            d.mkdir()

        # song1: f1 and f2 agree on title "Alpha", f3 has wrong title "Wrong"
        _create_mp3(f1 / "01 - song1.mp3", title="Alpha", track="1")
        _create_mp3(f2 / "01 - song1.mp3", title="Alpha", track="1")
        _create_mp3(f3 / "01 - song1.mp3", title="Wrong", track="1")

        # song2: all 3 have correct title, but f3 has wrong track number
        _create_mp3(f1 / "02 - song2.mp3", title="Beta", track="2")
        _create_mp3(f2 / "02 - song2.mp3", title="Beta", track="2")
        _create_mp3(f3 / "02 - song2.mp3", title="Beta", track="99")

        code, out, err = _run_main(str(f1), str(f2), str(f3), "--apply")
        assert code == 0

        # song1: f3 title should now be "Alpha"
        assert _read_title(f3 / "01 - song1.mp3") == "Alpha"
        # song1: title in f1 and f2 should be unchanged
        assert _read_title(f1 / "01 - song1.mp3") == "Alpha"
        assert _read_title(f2 / "01 - song1.mp3") == "Alpha"

        # song2: f3 track should now be 2
        assert _read_track(f3 / "02 - song2.mp3") == 2
        # song2: other files should be unchanged
        assert _read_track(f1 / "02 - song2.mp3") == 2
        assert _read_track(f2 / "02 - song2.mp3") == 2

        assert "files modified" in out
