from __future__ import annotations

from pathlib import Path

from id3_correction.models import (
    AnalysisResult,
    Conflict,
    Correction,
    FileGroup,
    FileRecord,
    MissingFile,
    ScanResult,
)
from id3_correction.reporter import generate_report, _format_value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _folder(name: str) -> Path:
    return Path(f"/albums/{name}")


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


def _empty_scan(folders: list[Path]) -> ScanResult:
    return ScanResult(file_groups={}, warnings=[])


# ---------------------------------------------------------------------------
# _format_value
# ---------------------------------------------------------------------------

class TestFormatValue:
    def test_none_returns_empty(self):
        assert _format_value("title", None) == "(empty)"

    def test_title_is_quoted(self):
        assert _format_value("title", "River") == '"River"'

    def test_track_is_plain(self):
        assert _format_value("track", 7) == "7"

    def test_track_none_returns_empty(self):
        assert _format_value("track", None) == "(empty)"


# ---------------------------------------------------------------------------
# generate_report — structure
# ---------------------------------------------------------------------------

class TestReportStructure:
    def _make_folders(self, names):
        return [_folder(n) for n in names]

    def test_empty_report_has_summary_and_totals(self):
        sr = ScanResult(file_groups={}, warnings=[])
        ar = AnalysisResult()
        report = generate_report(sr, ar, self._make_folders(["f1", "f2"]))
        assert "=== SCAN SUMMARY ===" in report
        assert "=== TOTALS ===" in report
        assert "Corrections to apply: 0" in report
        assert "Conflicts to resolve: 0" in report
        assert "Missing files flagged: 0" in report

    def test_no_warnings_section_when_empty(self):
        sr = ScanResult(file_groups={}, warnings=[])
        ar = AnalysisResult()
        report = generate_report(sr, ar, self._make_folders(["f1"]))
        assert "=== WARNINGS ===" not in report

    def test_no_missing_files_section_when_empty(self):
        sr = ScanResult(file_groups={}, warnings=[])
        ar = AnalysisResult()
        report = generate_report(sr, ar, self._make_folders(["f1"]))
        assert "=== MISSING FILES ===" not in report

    def test_no_conflicts_section_when_empty(self):
        sr = ScanResult(file_groups={}, warnings=[])
        ar = AnalysisResult()
        report = generate_report(sr, ar, self._make_folders(["f1"]))
        assert "=== CONFLICTS" not in report

    def test_no_corrections_section_when_empty(self):
        sr = ScanResult(file_groups={}, warnings=[])
        ar = AnalysisResult()
        report = generate_report(sr, ar, self._make_folders(["f1"]))
        assert "=== CORRECTIONS" not in report

    def test_all_sections_present_when_populated(self):
        rec1 = _rec("song", "f1", title="A", track=1)
        rec2 = _rec("song", "f2", title="B", track=2)
        group = _group("song", [rec1, rec2])
        sr = ScanResult(
            file_groups={"song": group},
            warnings=["[WARN] /albums/f1/song.flac — non-MP3 file, skipped"],
        )
        correction = Correction(
            file=rec1,
            tag="title",
            old_value="A",
            new_value="B",
            source="majority",
            auto_apply=True,
        )
        conflict = Conflict(
            identity="song",
            tag="title",
            values={"A": ["f1"], "B": ["f2"]},
        )
        mf = MissingFile(identity="other", missing_from=[_folder("f3")])
        ar = AnalysisResult(
            corrections=[correction],
            conflicts=[conflict],
            missing_files=[mf],
            missing_tags=[("song2", "title")],
        )
        report = generate_report(sr, ar, self._make_folders(["f1", "f2", "f3"]))

        assert "=== SCAN SUMMARY ===" in report
        assert "=== WARNINGS ===" in report
        assert "=== MISSING FILES ===" in report
        assert "=== MISSING TAGS ===" in report
        assert "=== CONFLICTS" in report
        assert "=== CORRECTIONS" in report
        assert "=== TOTALS ===" in report

    def test_summary_counts(self):
        rec1 = _rec("song", "f1", title="A", track=1)
        rec2 = _rec("song", "f2", title="A", track=1)
        group = _group("song", [rec1, rec2])
        sr = ScanResult(file_groups={"song": group}, warnings=[])
        ar = AnalysisResult()
        folders = self._make_folders(["f1", "f2"])
        report = generate_report(sr, ar, folders)
        assert "Folders: 2" in report
        assert "Total files scanned: 2" in report
        assert "File identities: 1" in report

    def test_correction_formatting_old_none(self):
        rec = _rec("song", "f1", title=None, track=None)
        corr = Correction(
            file=rec,
            tag="title",
            old_value=None,
            new_value="River",
            source="majority",
            auto_apply=True,
        )
        ar = AnalysisResult(corrections=[corr])
        sr = ScanResult(file_groups={}, warnings=[])
        report = generate_report(sr, ar, [_folder("f1")])
        assert "(empty)" in report
        assert '"River"' in report

    def test_fallback_correction_shows_source_and_marker(self):
        rec = _rec("07 - River", "f1", title="River", track=None)
        corr = Correction(
            file=rec,
            tag="track",
            old_value=None,
            new_value=7,
            source="filename",
            auto_apply=False,
        )
        ar = AnalysisResult(corrections=[corr])
        sr = ScanResult(file_groups={}, warnings=[])
        report = generate_report(sr, ar, [_folder("f1")])
        assert "[source: filename]" in report
        assert "requires confirmation" in report

    def test_conflict_shows_values_and_folders(self):
        conflict = Conflict(
            identity="03 - Mountain",
            tag="title",
            values={"Mountain": ["folder1", "folder2", "folder4"], "The Mountain": ["folder3", "folder5"]},
        )
        ar = AnalysisResult(conflicts=[conflict])
        sr = ScanResult(file_groups={}, warnings=[])
        report = generate_report(sr, ar, [_folder(f"folder{i}") for i in range(1, 6)])
        assert '"Mountain"' in report
        assert '"The Mountain"' in report
        assert "folder1" in report
        assert "No strict majority" in report

    def test_missing_file_shows_identity_and_folder(self):
        mf = MissingFile(identity="05 - River", missing_from=[_folder("f2")])
        ar = AnalysisResult(missing_files=[mf])
        sr = ScanResult(file_groups={}, warnings=[])
        report = generate_report(sr, ar, [_folder("f1"), _folder("f2")])
        assert '"05 - River"' in report
        assert "not found in" in report

    def test_sections_in_correct_order(self):
        rec = _rec("song", "f1", title="A", track=None)
        corr = Correction(
            file=rec,
            tag="track",
            old_value=None,
            new_value=5,
            source="filename",
            auto_apply=False,
        )
        mf = MissingFile(identity="other", missing_from=[_folder("f2")])
        conflict = Conflict(identity="song", tag="title", values={"A": ["f1"], "B": ["f2"]})
        ar = AnalysisResult(
            corrections=[corr],
            conflicts=[conflict],
            missing_files=[mf],
            missing_tags=[("song", "title")],
        )
        sr = ScanResult(file_groups={}, warnings=["[WARN] something"])
        report = generate_report(sr, ar, [_folder("f1"), _folder("f2")])

        pos_summary = report.index("=== SCAN SUMMARY ===")
        pos_warnings = report.index("=== WARNINGS ===")
        pos_missing_files = report.index("=== MISSING FILES ===")
        pos_missing_tags = report.index("=== MISSING TAGS ===")
        pos_conflicts = report.index("=== CONFLICTS")
        pos_corrections = report.index("=== CORRECTIONS")
        pos_totals = report.index("=== TOTALS ===")

        assert pos_summary < pos_warnings < pos_missing_files < pos_missing_tags
        assert pos_missing_tags < pos_conflicts < pos_corrections < pos_totals
