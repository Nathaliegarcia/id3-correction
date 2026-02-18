from __future__ import annotations

from pathlib import Path

import pytest

from id3_correction.analyzer import (
    _detect_missing_files,
    _resolve_title,
    _resolve_track,
    _strict_majority,
    _track_from_filename,
    _track_from_title_match,
    analyze,
)
from id3_correction.models import FileGroup, FileRecord, ScanResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _folder(name: str) -> Path:
    return Path(f"/tmp/{name}")


def _rec(identity: str, folder: str, title: str | None = None, track: int | None = None) -> FileRecord:
    f = _folder(folder)
    return FileRecord(
        path=f / f"{identity}.mp3",
        folder=f,
        identity=identity,
        title=title,
        track=track,
    )


def _group(identity: str, records: list[FileRecord]) -> FileGroup:
    return FileGroup(identity=identity, files=records)


# ---------------------------------------------------------------------------
# _strict_majority
# ---------------------------------------------------------------------------

class TestStrictMajority:
    def test_clear_majority(self):
        assert _strict_majority(["A", "A", "B"], 3) == "A"

    def test_no_majority_equal_split(self):
        assert _strict_majority(["A", "B"], 2) is None

    def test_unanimous(self):
        assert _strict_majority([5, 5, 5], 3) == 5

    def test_5_folders_3_vs_2(self):
        assert _strict_majority([1, 1, 1, 2, 2], 5) == 1

    def test_empty_values(self):
        assert _strict_majority([], 3) is None

    def test_exactly_50_percent_not_majority(self):
        # 2/4 = 50% exactly — NOT a strict majority
        assert _strict_majority(["A", "A", "B", "B"], 4) is None

    def test_single_value(self):
        assert _strict_majority(["X"], 1) == "X"


# ---------------------------------------------------------------------------
# _resolve_title
# ---------------------------------------------------------------------------

class TestResolveTitle:
    def test_all_same_title_no_corrections(self):
        group = _group("song", [
            _rec("song", "f1", title="River"),
            _rec("song", "f2", title="River"),
            _rec("song", "f3", title="River"),
        ])
        corrs, conflicts, missing = _resolve_title(group, [_folder("f1"), _folder("f2"), _folder("f3")])
        assert corrs == []
        assert conflicts == []
        assert missing == []

    def test_majority_title_one_outlier(self):
        group = _group("song", [
            _rec("song", "f1", title="River"),
            _rec("song", "f2", title="River"),
            _rec("song", "f3", title="Wrong"),
        ])
        corrs, conflicts, missing = _resolve_title(group, [_folder("f1"), _folder("f2"), _folder("f3")])
        assert len(corrs) == 1
        assert corrs[0].new_value == "River"
        assert corrs[0].file.folder == _folder("f3")
        assert corrs[0].source == "majority"
        assert corrs[0].auto_apply is True
        assert conflicts == []

    def test_missing_title_filled_by_majority(self):
        group = _group("song", [
            _rec("song", "f1", title="River"),
            _rec("song", "f2", title="River"),
            _rec("song", "f3", title=None),
        ])
        corrs, conflicts, missing = _resolve_title(group, [_folder("f1"), _folder("f2"), _folder("f3")])
        assert len(corrs) == 1
        assert corrs[0].old_value is None
        assert corrs[0].new_value == "River"

    def test_two_folders_different_titles_conflict(self):
        group = _group("song", [
            _rec("song", "f1", title="River"),
            _rec("song", "f2", title="The River"),
        ])
        corrs, conflicts, missing = _resolve_title(group, [_folder("f1"), _folder("f2")])
        assert corrs == []
        assert len(conflicts) == 1
        assert conflicts[0].tag == "title"
        assert "River" in conflicts[0].values
        assert "The River" in conflicts[0].values

    def test_5_folders_3_vs_2_majority_wins(self):
        group = _group("song", [
            _rec("song", "f1", title="Mountain"),
            _rec("song", "f2", title="Mountain"),
            _rec("song", "f3", title="Mountain"),
            _rec("song", "f4", title="The Mountain"),
            _rec("song", "f5", title="The Mountain"),
        ])
        corrs, conflicts, missing = _resolve_title(group, [_folder(f"f{i}") for i in range(1, 6)])
        assert len(corrs) == 2  # f4 and f5 corrected
        assert all(c.new_value == "Mountain" for c in corrs)
        assert conflicts == []

    def test_all_files_missing_title(self):
        group = _group("song", [
            _rec("song", "f1", title=None),
            _rec("song", "f2", title=None),
        ])
        corrs, conflicts, missing = _resolve_title(group, [_folder("f1"), _folder("f2")])
        assert corrs == []
        assert conflicts == []
        assert ("song", "title") in missing


# ---------------------------------------------------------------------------
# _resolve_track (majority part only — fallback tested in test step 5)
# ---------------------------------------------------------------------------

class TestResolveTrack:
    def test_all_same_track_no_corrections(self):
        group = _group("song", [
            _rec("song", "f1", track=5),
            _rec("song", "f2", track=5),
            _rec("song", "f3", track=5),
        ])
        corrs, conflicts, missing = _resolve_track(group, [_folder("f1"), _folder("f2"), _folder("f3")])
        assert corrs == []
        assert conflicts == []

    def test_majority_track_one_outlier(self):
        group = _group("song", [
            _rec("song", "f1", track=3),
            _rec("song", "f2", track=3),
            _rec("song", "f3", track=99),
        ])
        corrs, conflicts, missing = _resolve_track(group, [_folder("f1"), _folder("f2"), _folder("f3")])
        assert len(corrs) == 1
        assert corrs[0].new_value == 3
        assert corrs[0].source == "majority"
        assert corrs[0].auto_apply is True

    def test_missing_track_filled_by_majority(self):
        group = _group("song", [
            _rec("song", "f1", track=7),
            _rec("song", "f2", track=7),
            _rec("song", "f3", track=None),
        ])
        corrs, conflicts, missing = _resolve_track(group, [_folder("f1"), _folder("f2"), _folder("f3")])
        assert len(corrs) == 1
        assert corrs[0].old_value is None
        assert corrs[0].new_value == 7

    def test_two_folders_different_tracks_conflict(self):
        group = _group("song", [
            _rec("song", "f1", track=1),
            _rec("song", "f2", track=2),
        ])
        corrs, conflicts, missing = _resolve_track(group, [_folder("f1"), _folder("f2")])
        assert corrs == []
        assert len(conflicts) == 1
        assert conflicts[0].tag == "track"

    def test_5_folders_3_vs_2_track_majority(self):
        group = _group("song", [
            _rec("song", "f1", track=5),
            _rec("song", "f2", track=5),
            _rec("song", "f3", track=5),
            _rec("song", "f4", track=6),
            _rec("song", "f5", track=6),
        ])
        corrs, conflicts, missing = _resolve_track(group, [_folder(f"f{i}") for i in range(1, 6)])
        assert len(corrs) == 2
        assert all(c.new_value == 5 for c in corrs)
        assert conflicts == []

    def test_all_tracks_missing_flags_as_missing(self):
        group = _group("song", [
            _rec("song", "f1", track=None),
            _rec("song", "f2", track=None),
        ])
        corrs, conflicts, missing = _resolve_track(group, [_folder("f1"), _folder("f2")])
        # No corrections, no conflicts — missing tag flagged (fallback stub returns missing)
        assert corrs == []
        assert conflicts == []
        assert ("song", "track") in missing


# ---------------------------------------------------------------------------
# _detect_missing_files
# ---------------------------------------------------------------------------

class TestDetectMissingFiles:
    def test_file_present_everywhere(self):
        group = _group("song", [
            _rec("song", "f1"),
            _rec("song", "f2"),
            _rec("song", "f3"),
        ])
        result = _detect_missing_files(group, [_folder("f1"), _folder("f2"), _folder("f3")])
        assert result is None

    def test_file_missing_from_one_folder(self):
        group = _group("song", [
            _rec("song", "f1"),
            _rec("song", "f2"),
        ])
        all_folders = [_folder("f1"), _folder("f2"), _folder("f3")]
        result = _detect_missing_files(group, all_folders)
        assert result is not None
        assert result.identity == "song"
        assert _folder("f3") in result.missing_from

    def test_file_in_only_one_folder(self):
        group = _group("song", [_rec("song", "f1")])
        all_folders = [_folder("f1"), _folder("f2"), _folder("f3")]
        result = _detect_missing_files(group, all_folders)
        assert result is not None
        assert len(result.missing_from) == 2


# ---------------------------------------------------------------------------
# analyze() integration
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_all_in_sync(self):
        rec1 = _rec("song", "f1", title="River", track=5)
        rec2 = _rec("song", "f2", title="River", track=5)
        group = _group("song", [rec1, rec2])
        sr = ScanResult(file_groups={"song": group})
        result = analyze(sr, [_folder("f1"), _folder("f2")])
        assert result.corrections == []
        assert result.conflicts == []
        assert result.missing_files == []

    def test_multiple_groups_corrections(self):
        group1 = _group("song1", [
            _rec("song1", "f1", title="A", track=1),
            _rec("song1", "f2", title="A", track=1),
            _rec("song1", "f3", title="B", track=1),
        ])
        group2 = _group("song2", [
            _rec("song2", "f1", title="X", track=2),
            _rec("song2", "f2", title="X", track=2),
            _rec("song2", "f3", title="X", track=2),
        ])
        sr = ScanResult(file_groups={"song1": group1, "song2": group2})
        result = analyze(sr, [_folder(f"f{i}") for i in range(1, 4)])
        # song1 has a title conflict correction, song2 has none
        title_corrs = [c for c in result.corrections if c.tag == "title"]
        assert len(title_corrs) == 1
        assert title_corrs[0].new_value == "A"


# ---------------------------------------------------------------------------
# Step 5: Fallback track resolution
# ---------------------------------------------------------------------------

class TestTrackFromFilename:
    def test_leading_number_with_separator(self):
        assert _track_from_filename("07 - River") == 7

    def test_leading_number_dot_separator(self):
        assert _track_from_filename("12.Song") == 12

    def test_leading_number_underscore(self):
        assert _track_from_filename("03_title") == 3

    def test_leading_number_only(self):
        assert _track_from_filename("3") == 3

    def test_leading_zero(self):
        assert _track_from_filename("05 - Track") == 5

    def test_no_leading_number(self):
        assert _track_from_filename("River") is None

    def test_number_in_middle_no_match(self):
        assert _track_from_filename("song2you") is None

    def test_number_at_end_only_no_match(self):
        assert _track_from_filename("track5") is None


class TestTrackFromTitleMatch:
    def test_matching_title_in_other_group(self):
        # "River.mp3" has title "River" but no track
        group_no_track = _group("River", [
            _rec("River", "f1", title="River", track=None),
            _rec("River", "f2", title="River", track=None),
        ])
        # "07 - River.mp3" has title "River" and track 7
        group_with_track = _group("07 - River", [
            _rec("07 - River", "f1", title="River", track=7),
            _rec("07 - River", "f2", title="River", track=7),
        ])
        all_groups = {"River": group_no_track, "07 - River": group_with_track}
        result = _track_from_title_match(group_no_track, all_groups)
        assert result == 7

    def test_no_matching_title(self):
        group = _group("River", [
            _rec("River", "f1", title="River", track=None),
        ])
        other_group = _group("Mountain", [
            _rec("Mountain", "f1", title="Mountain", track=3),
        ])
        all_groups = {"River": group, "Mountain": other_group}
        result = _track_from_title_match(group, all_groups)
        assert result is None

    def test_no_title_in_group_returns_none(self):
        group = _group("River", [
            _rec("River", "f1", title=None, track=None),
        ])
        other_group = _group("07 - River", [
            _rec("07 - River", "f1", title="River", track=7),
        ])
        all_groups = {"River": group, "07 - River": other_group}
        result = _track_from_title_match(group, all_groups)
        assert result is None


class TestFallbackCorrectionSource:
    def test_filename_fallback_sets_source_and_no_auto_apply(self):
        group = _group("07 - River", [
            _rec("07 - River", "f1", title="River", track=None),
            _rec("07 - River", "f2", title="River", track=None),
        ])
        all_groups = {"07 - River": group}
        corrs, conflicts, missing = _resolve_track(
            group, [_folder("f1"), _folder("f2")], all_groups
        )
        assert len(corrs) == 2
        assert all(c.source == "filename" for c in corrs)
        assert all(c.auto_apply is False for c in corrs)
        assert all(c.new_value == 7 for c in corrs)
        assert missing == []

    def test_title_match_fallback_sets_source_and_no_auto_apply(self):
        group_no_track = _group("River", [
            _rec("River", "f1", title="River", track=None),
        ])
        group_with_track = _group("07 - River", [
            _rec("07 - River", "f1", title="River", track=7),
        ])
        all_groups = {"River": group_no_track, "07 - River": group_with_track}
        corrs, conflicts, missing = _resolve_track(
            group_no_track, [_folder("f1")], all_groups
        )
        assert len(corrs) == 1
        assert corrs[0].source == "title_match"
        assert corrs[0].auto_apply is False
        assert corrs[0].new_value == 7

    def test_no_fallback_possible_flags_as_missing(self):
        group = _group("River", [
            _rec("River", "f1", title="River", track=None),
        ])
        all_groups = {"River": group}
        corrs, conflicts, missing = _resolve_track(
            group, [_folder("f1")], all_groups
        )
        assert corrs == []
        assert ("River", "track") in missing
