from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileRecord:
    path: Path
    folder: Path
    identity: str
    title: str | None
    track: int | None


@dataclass
class FileGroup:
    identity: str
    files: list[FileRecord] = field(default_factory=list)


@dataclass
class Correction:
    file: FileRecord
    tag: str  # "title" or "track"
    old_value: str | int | None
    new_value: str | int
    source: str  # "majority", "filename", "title_match"
    auto_apply: bool  # True only when source == "majority"


@dataclass
class Conflict:
    identity: str
    tag: str  # "title" or "track"
    values: dict[str, list[str]]  # value -> list of folder names


@dataclass
class MissingFile:
    identity: str
    missing_from: list[Path]


@dataclass
class AnalysisResult:
    corrections: list[Correction] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    missing_files: list[MissingFile] = field(default_factory=list)
    missing_tags: list[tuple[str, str]] = field(default_factory=list)
    # missing_tags entries: (identity, tag_name)


@dataclass
class ScanResult:
    file_groups: dict[str, FileGroup] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
