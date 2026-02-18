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


def _make_record(identity="song", title="Title", track=1, folder="/f1"):
    folder_path = Path(folder)
    return FileRecord(
        path=folder_path / f"{identity}.mp3",
        folder=folder_path,
        identity=identity,
        title=title,
        track=track,
    )


class TestFileRecord:
    def test_construction(self):
        rec = _make_record()
        assert rec.identity == "song"
        assert rec.title == "Title"
        assert rec.track == 1

    def test_none_fields(self):
        rec = _make_record(title=None, track=None)
        assert rec.title is None
        assert rec.track is None


class TestFileGroup:
    def test_construction(self):
        rec1 = _make_record(folder="/f1")
        rec2 = _make_record(folder="/f2")
        group = FileGroup(identity="song", files=[rec1, rec2])
        assert group.identity == "song"
        assert len(group.files) == 2

    def test_default_empty_files(self):
        group = FileGroup(identity="song")
        assert group.files == []


class TestCorrection:
    def test_majority_correction(self):
        rec = _make_record()
        corr = Correction(
            file=rec,
            tag="title",
            old_value=None,
            new_value="New Title",
            source="majority",
            auto_apply=True,
        )
        assert corr.source == "majority"
        assert corr.auto_apply is True

    def test_filename_correction_not_auto_apply(self):
        rec = _make_record()
        corr = Correction(
            file=rec,
            tag="track",
            old_value=None,
            new_value=5,
            source="filename",
            auto_apply=False,
        )
        assert corr.auto_apply is False

    def test_title_match_correction_not_auto_apply(self):
        rec = _make_record()
        corr = Correction(
            file=rec,
            tag="track",
            old_value=None,
            new_value=7,
            source="title_match",
            auto_apply=False,
        )
        assert corr.source == "title_match"
        assert corr.auto_apply is False


class TestConflict:
    def test_construction(self):
        conflict = Conflict(
            identity="03 - Mountain",
            tag="title",
            values={"Mountain": ["folder1", "folder2"], "The Mountain": ["folder3"]},
        )
        assert conflict.tag == "title"
        assert "Mountain" in conflict.values
        assert conflict.values["Mountain"] == ["folder1", "folder2"]


class TestMissingFile:
    def test_construction(self):
        mf = MissingFile(
            identity="05 - River",
            missing_from=[Path("/folder2"), Path("/folder3")],
        )
        assert mf.identity == "05 - River"
        assert len(mf.missing_from) == 2


class TestAnalysisResult:
    def test_default_empty(self):
        result = AnalysisResult()
        assert result.corrections == []
        assert result.conflicts == []
        assert result.missing_files == []
        assert result.missing_tags == []

    def test_with_missing_tags(self):
        result = AnalysisResult(missing_tags=[("song", "title"), ("song", "track")])
        assert len(result.missing_tags) == 2


class TestScanResult:
    def test_default_empty(self):
        sr = ScanResult()
        assert sr.file_groups == {}
        assert sr.warnings == []

    def test_with_groups_and_warnings(self):
        rec = _make_record()
        group = FileGroup(identity="song", files=[rec])
        sr = ScanResult(
            file_groups={"song": group},
            warnings=["non-mp3 file skipped"],
        )
        assert "song" in sr.file_groups
        assert len(sr.warnings) == 1
