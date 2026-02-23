from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import TypeVar

from id3_correction.models import (
    AnalysisResult,
    Conflict,
    Correction,
    FileGroup,
    MissingFile,
    ScanResult,
)

T = TypeVar("T")


def analyze(scan_result: ScanResult, all_folders: list[Path]) -> AnalysisResult:
    """Analyze all file groups and produce corrections, conflicts, and flags."""
    corrections: list[Correction] = []
    conflicts: list[Conflict] = []
    missing_files: list[MissingFile] = []
    missing_tags: list[tuple[str, str]] = []

    all_groups = scan_result.file_groups

    for identity, group in all_groups.items():
        # Missing files
        mf = _detect_missing_files(group, all_folders)
        if mf is not None:
            missing_files.append(mf)

        # Title resolution
        title_corrs, title_conflicts, title_missing = _resolve_title(group, all_folders)
        corrections.extend(title_corrs)
        conflicts.extend(title_conflicts)
        missing_tags.extend(title_missing)

        # Track resolution
        track_corrs, track_conflicts, track_missing = _resolve_track(
            group, all_folders, all_groups
        )
        corrections.extend(track_corrs)
        conflicts.extend(track_conflicts)
        missing_tags.extend(track_missing)

    return AnalysisResult(
        corrections=corrections,
        conflicts=conflicts,
        missing_files=missing_files,
        missing_tags=missing_tags,
    )


def _resolve_title(
    group: FileGroup, all_folders: list[Path]
) -> tuple[list[Correction], list[Conflict], list[tuple[str, str]]]:
    corrections: list[Correction] = []
    conflicts: list[Conflict] = []
    missing: list[tuple[str, str]] = []

    total = len(group.files)
    titles = [f.title for f in group.files if f.title is not None]

    if not titles:
        missing.append((group.identity, "title"))
        return corrections, conflicts, missing

    canonical = _strict_majority(titles, total)

    if canonical is not None:
        for f in group.files:
            if f.title != canonical:
                corrections.append(
                    Correction(
                        file=f,
                        tag="title",
                        old_value=f.title,
                        new_value=canonical,
                        source="majority",
                        auto_apply=True,
                    )
                )
    else:
        # Build values dict: value -> list of folder names
        counter = Counter(titles)
        values: dict[str, list[str]] = {}
        for f in group.files:
            if f.title is not None:
                folder_name = f.folder.name
                if f.title not in values:
                    values[f.title] = []
                values[f.title].append(folder_name)
        # Also include files with None title — they don't vote but are affected
        conflicts.append(Conflict(identity=group.identity, tag="title", values=values))

    return corrections, conflicts, missing


def _resolve_track(
    group: FileGroup,
    all_folders: list[Path],
    all_groups: dict[str, FileGroup] | None = None,
) -> tuple[list[Correction], list[Conflict], list[tuple[str, str]]]:
    corrections: list[Correction] = []
    conflicts: list[Conflict] = []
    missing: list[tuple[str, str]] = []

    total = len(group.files)
    tracks = [f.track for f in group.files if f.track is not None]

    if tracks:
        canonical = _strict_majority(tracks, total)
        if canonical is not None:
            for f in group.files:
                if f.track != canonical:
                    corrections.append(
                        Correction(
                            file=f,
                            tag="track",
                            old_value=f.track,
                            new_value=canonical,
                            source="majority",
                            auto_apply=True,
                        )
                    )
        else:
            # Conflict — build values dict (str keys)
            values: dict[str, list[str]] = {}
            for f in group.files:
                if f.track is not None:
                    key = str(f.track)
                    folder_name = f.folder.name
                    if key not in values:
                        values[key] = []
                    values[key].append(folder_name)
            conflicts.append(
                Conflict(identity=group.identity, tag="track", values=values)
            )
    else:
        # No tracks anywhere — attempt fallback chain
        fallback_corrs, fallback_missing = _resolve_track_fallback(
            group, all_groups or {}
        )
        corrections.extend(fallback_corrs)
        missing.extend(fallback_missing)

    return corrections, conflicts, missing


def _resolve_track_fallback(
    group: FileGroup,
    all_groups: dict[str, FileGroup],
) -> tuple[list[Correction], list[tuple[str, str]]]:
    """Fallback track resolution when no file in the group has a track tag."""
    corrections: list[Correction] = []
    missing: list[tuple[str, str]] = []

    # 1. Filename fallback
    track = _track_from_filename(group.identity)
    source = "filename"

    if track is None:
        # 2. Title-match fallback
        track = _track_from_title_match(group, all_groups)
        source = "title_match"

    if track is not None:
        for f in group.files:
            corrections.append(
                Correction(
                    file=f,
                    tag="track",
                    old_value=f.track,
                    new_value=track,
                    source=source,
                    auto_apply=False,
                )
            )
    else:
        missing.append((group.identity, "track"))

    return corrections, missing


def _track_from_filename(identity: str) -> int | None:
    """Extract track number from a leading digit sequence in the identity.

    Only matches digits at the start followed by a separator character or end of
    string. This avoids false positives like 'song2you'.
    """
    m = re.match(r"^(\d+)(?:\s*[-_.\s]|$)", identity)
    if m:
        return int(m.group(1))
    return None


def _track_from_title_match(
    group: FileGroup, all_groups: dict[str, FileGroup]
) -> int | None:
    """Find track number from another group that shares the same canonical title."""
    # Determine canonical title for this group
    total = len(group.files)
    titles = [f.title for f in group.files if f.title is not None]
    if not titles:
        return None

    canonical_title = _strict_majority(titles, total)
    if canonical_title is None:
        # Use the only known title if there is exactly one unique title
        unique = list(set(titles))
        if len(unique) == 1:
            canonical_title = unique[0]
        else:
            return None

    # Search other groups for matching title and resolved track
    for other_identity, other_group in all_groups.items():
        if other_identity == group.identity:
            continue
        other_tracks = [f.track for f in other_group.files if f.track is not None]
        if not other_tracks:
            continue
        other_canonical_track = _strict_majority(other_tracks, len(other_group.files))
        if other_canonical_track is None:
            continue
        other_titles = [f.title for f in other_group.files if f.title is not None]
        if not other_titles:
            continue
        other_canonical_title = _strict_majority(other_titles, len(other_group.files))
        if other_canonical_title is None:
            unique = list(set(other_titles))
            if len(unique) == 1:
                other_canonical_title = unique[0]
            else:
                continue
        if other_canonical_title == canonical_title:
            return other_canonical_track

    return None


def _strict_majority(values: list[T], total: int) -> T | None:
    """Return value that appears more than total/2 times, or None."""
    if not values:
        return None
    counter: Counter = Counter(values)
    most_common_value, most_common_count = counter.most_common(1)[0]
    if most_common_count > total / 2:
        return most_common_value
    return None


def _detect_missing_files(
    group: FileGroup, all_folders: list[Path]
) -> MissingFile | None:
    """Return MissingFile if the identity is absent from some folders."""
    present_folders = {f.folder for f in group.files}
    missing_from = [folder for folder in all_folders if folder not in present_folders]
    if missing_from:
        return MissingFile(identity=group.identity, missing_from=missing_from)
    return None
