from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TRCK

from id3_correction.applier import (
    _prompt_choice,
    _prompt_yes_no,
    _write_tag,
    apply_corrections_with_groups,
)
from id3_correction.models import (
    AnalysisResult,
    Conflict,
    Correction,
    FileGroup,
    FileRecord,
    MissingFile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_mp3(path: Path, title: str | None = None, track: str | None = None) -> Path:
    """Create a minimal MP3 test file with optional ID3 tags."""
    path.write_bytes(b"")
    if title is not None or track is not None:
        tags = ID3()
        if title is not None:
            tags.add(TIT2(encoding=3, text=title))
        if track is not None:
            tags.add(TRCK(encoding=3, text=track))
        tags.save(str(path))
    return path


def _rec(path: Path, folder: Path, identity: str, title: str | None = None, track: int | None = None) -> FileRecord:
    return FileRecord(path=path, folder=folder, identity=identity, title=title, track=track)


# ---------------------------------------------------------------------------
# _write_tag
# ---------------------------------------------------------------------------

class TestWriteTag:
    def test_write_title(self, tmp_path):
        mp3 = tmp_path / "song.mp3"
        _create_mp3(mp3)
        _write_tag(mp3, "title", "My Song")
        tags = ID3(str(mp3))
        assert str(tags["TIT2"]) == "My Song"

    def test_write_track(self, tmp_path):
        mp3 = tmp_path / "song.mp3"
        _create_mp3(mp3)
        _write_tag(mp3, "track", 5)
        tags = ID3(str(mp3))
        assert str(tags["TRCK"]) == "5"

    def test_write_to_file_with_no_existing_tags(self, tmp_path):
        mp3 = tmp_path / "song.mp3"
        mp3.write_bytes(b"")  # no ID3 at all
        _write_tag(mp3, "title", "New Title")
        tags = ID3(str(mp3))
        assert str(tags["TIT2"]) == "New Title"

    def test_overwrite_existing_title(self, tmp_path):
        mp3 = tmp_path / "song.mp3"
        _create_mp3(mp3, title="Old Title")
        _write_tag(mp3, "title", "New Title")
        tags = ID3(str(mp3))
        assert str(tags["TIT2"]) == "New Title"

    def test_overwrite_existing_track(self, tmp_path):
        mp3 = tmp_path / "song.mp3"
        _create_mp3(mp3, track="3")
        _write_tag(mp3, "track", 7)
        tags = ID3(str(mp3))
        assert str(tags["TRCK"]) == "7"


# ---------------------------------------------------------------------------
# apply_corrections_with_groups — majority + auto_apply flag
# ---------------------------------------------------------------------------

class TestApplyCorrections:
    def _make_corr(self, mp3: Path, folder: Path, tag: str, new_value, source: str, auto_apply: bool) -> Correction:
        rec = _rec(mp3, folder, mp3.stem, title=None, track=None)
        return Correction(
            file=rec,
            tag=tag,
            old_value=None,
            new_value=new_value,
            source=source,
            auto_apply=auto_apply,
        )

    def test_majority_auto_apply_no_prompt(self, tmp_path):
        mp3 = tmp_path / "song.mp3"
        _create_mp3(mp3)
        folder = tmp_path
        corr = self._make_corr(mp3, folder, "title", "River", "majority", True)
        ar = AnalysisResult(corrections=[corr])

        # With auto_apply=True, no stdin should be read
        with patch("sys.stdin", io.StringIO("")):
            n = apply_corrections_with_groups(ar, {}, auto_apply=True)

        assert n == 1
        tags = ID3(str(mp3))
        assert str(tags["TIT2"]) == "River"

    def test_majority_prompt_yes(self, tmp_path):
        mp3 = tmp_path / "song.mp3"
        _create_mp3(mp3)
        folder = tmp_path
        corr = self._make_corr(mp3, folder, "title", "River", "majority", True)
        ar = AnalysisResult(corrections=[corr])

        with patch("sys.stdin", io.StringIO("y\n")):
            n = apply_corrections_with_groups(ar, {}, auto_apply=False)

        assert n == 1
        tags = ID3(str(mp3))
        assert str(tags["TIT2"]) == "River"

    def test_majority_prompt_no(self, tmp_path):
        mp3 = tmp_path / "song.mp3"
        _create_mp3(mp3)
        folder = tmp_path
        corr = self._make_corr(mp3, folder, "title", "River", "majority", True)
        ar = AnalysisResult(corrections=[corr])

        with patch("sys.stdin", io.StringIO("n\n")):
            n = apply_corrections_with_groups(ar, {}, auto_apply=False)

        assert n == 0
        # Title should not have been written
        try:
            tags = ID3(str(mp3))
            assert "TIT2" not in tags
        except ID3NoHeaderError:
            pass  # fine — no tags at all

    def test_fallback_correction_prompts_individually(self, tmp_path):
        mp3 = tmp_path / "07 - River.mp3"
        _create_mp3(mp3)
        folder = tmp_path
        corr = self._make_corr(mp3, folder, "track", 7, "filename", False)
        ar = AnalysisResult(corrections=[corr])

        with patch("sys.stdin", io.StringIO("y\n")):
            n = apply_corrections_with_groups(ar, {}, auto_apply=True)

        assert n == 1
        tags = ID3(str(mp3))
        assert str(tags["TRCK"]) == "7"

    def test_fallback_correction_declined(self, tmp_path):
        mp3 = tmp_path / "07 - River.mp3"
        _create_mp3(mp3)
        folder = tmp_path
        corr = self._make_corr(mp3, folder, "track", 7, "filename", False)
        ar = AnalysisResult(corrections=[corr])

        with patch("sys.stdin", io.StringIO("n\n")):
            n = apply_corrections_with_groups(ar, {}, auto_apply=True)

        assert n == 0

    def test_conflict_resolution_applies_chosen_value(self, tmp_path):
        mp3_1 = tmp_path / "f1" / "song.mp3"
        mp3_2 = tmp_path / "f2" / "song.mp3"
        (tmp_path / "f1").mkdir()
        (tmp_path / "f2").mkdir()
        _create_mp3(mp3_1, title="Mountain")
        _create_mp3(mp3_2, title="The Mountain")

        rec1 = _rec(mp3_1, tmp_path / "f1", "song", title="Mountain")
        rec2 = _rec(mp3_2, tmp_path / "f2", "song", title="The Mountain")
        group = FileGroup(identity="song", files=[rec1, rec2])

        conflict = Conflict(
            identity="song",
            tag="title",
            values={"Mountain": ["f1"], "The Mountain": ["f2"]},
        )
        ar = AnalysisResult(conflicts=[conflict])
        file_groups = {"song": group}

        # User chooses option 1 = "Mountain"
        with patch("sys.stdin", io.StringIO("1\n")):
            n = apply_corrections_with_groups(ar, file_groups, auto_apply=False)

        assert n == 1  # only rec2 (The Mountain) needs to change
        tags2 = ID3(str(mp3_2))
        assert str(tags2["TIT2"]) == "Mountain"

    def test_conflict_skip_no_writes(self, tmp_path):
        mp3_1 = tmp_path / "f1" / "song.mp3"
        mp3_2 = tmp_path / "f2" / "song.mp3"
        (tmp_path / "f1").mkdir()
        (tmp_path / "f2").mkdir()
        _create_mp3(mp3_1, title="Mountain")
        _create_mp3(mp3_2, title="The Mountain")

        rec1 = _rec(mp3_1, tmp_path / "f1", "song", title="Mountain")
        rec2 = _rec(mp3_2, tmp_path / "f2", "song", title="The Mountain")
        group = FileGroup(identity="song", files=[rec1, rec2])

        conflict = Conflict(
            identity="song",
            tag="title",
            values={"Mountain": ["f1"], "The Mountain": ["f2"]},
        )
        ar = AnalysisResult(conflicts=[conflict])
        file_groups = {"song": group}

        # User chooses 0 = skip
        with patch("sys.stdin", io.StringIO("0\n")):
            n = apply_corrections_with_groups(ar, file_groups, auto_apply=False)

        assert n == 0
        # Values should be unchanged
        tags1 = ID3(str(mp3_1))
        tags2 = ID3(str(mp3_2))
        assert str(tags1["TIT2"]) == "Mountain"
        assert str(tags2["TIT2"]) == "The Mountain"

    def test_returns_correct_modified_count(self, tmp_path):
        mp3_a = tmp_path / "a.mp3"
        mp3_b = tmp_path / "b.mp3"
        _create_mp3(mp3_a)
        _create_mp3(mp3_b)
        folder = tmp_path
        corr_a = self._make_corr(mp3_a, folder, "title", "A", "majority", True)
        corr_b = self._make_corr(mp3_b, folder, "title", "B", "majority", True)
        ar = AnalysisResult(corrections=[corr_a, corr_b])

        with patch("sys.stdin", io.StringIO("")):
            n = apply_corrections_with_groups(ar, {}, auto_apply=True)

        assert n == 2
