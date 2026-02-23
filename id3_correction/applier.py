from __future__ import annotations

import sys
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TRCK

from id3_correction.models import AnalysisResult, Conflict


def apply_corrections_with_groups(
    analysis: AnalysisResult,
    file_groups: dict,
    auto_apply: bool,
) -> int:
    """Apply corrections and resolve conflicts interactively.

    Returns the number of files actually modified.
    """
    modified_paths: set[Path] = set()

    # --- Majority-based corrections ---
    majority_corrs = [c for c in analysis.corrections if c.auto_apply]
    if majority_corrs:
        if auto_apply or _prompt_yes_no(
            f"Apply {len(majority_corrs)} majority-based corrections? [y/N] "
        ):
            for corr in majority_corrs:
                _write_tag(corr.file.path, corr.tag, corr.new_value)
                modified_paths.add(corr.file.path)

    # --- Fallback corrections (always prompted individually) ---
    fallback_corrs = [c for c in analysis.corrections if not c.auto_apply]
    for corr in fallback_corrs:
        msg = (
            f'Set {corr.tag} of "{corr.file.path}" to {corr.new_value} '
            f"[source: {corr.source}]? [y/N] "
        )
        if _prompt_yes_no(msg):
            _write_tag(corr.file.path, corr.tag, corr.new_value)
            modified_paths.add(corr.file.path)

    # --- Conflicts ---
    for conflict in analysis.conflicts:
        chosen_value = _prompt_choice(conflict)
        if chosen_value is None:
            continue

        group = file_groups.get(conflict.identity)
        if group is None:
            continue

        typed_value: str | int
        if conflict.tag == "track":
            try:
                typed_value = int(chosen_value)
            except ValueError:
                typed_value = chosen_value
        else:
            typed_value = chosen_value

        for file_rec in group.files:
            current = file_rec.title if conflict.tag == "title" else file_rec.track
            if current != typed_value:
                _write_tag(file_rec.path, conflict.tag, typed_value)
                modified_paths.add(file_rec.path)

    return len(modified_paths)


def _write_tag(file_path: Path, tag: str, value: str | int) -> None:
    """Write an ID3 tag to an MP3 file in-place."""
    try:
        tags = ID3(str(file_path))
    except ID3NoHeaderError:
        tags = ID3()

    if tag == "title":
        tags.delall("TIT2")
        tags.add(TIT2(encoding=3, text=str(value)))
    elif tag == "track":
        tags.delall("TRCK")
        tags.add(TRCK(encoding=3, text=str(value)))

    tags.save(str(file_path))


def _prompt_yes_no(message: str) -> bool:
    """Prompt user for yes/no. Returns True for y/Y."""
    sys.stdout.write(message)
    sys.stdout.flush()
    line = sys.stdin.readline().strip()
    return line.lower() == "y"


def _prompt_choice(conflict: Conflict) -> str | None:
    """Display numbered options for a conflict and return chosen value or None."""
    options = list(conflict.values.keys())
    print(f'\nConflict: "{conflict.identity}" — {conflict.tag}:')
    for i, value in enumerate(options, 1):
        folders = ", ".join(conflict.values[value])
        print(f"  {i}. {value!r}  (in: {folders})")
    print("  0. Skip")

    sys.stdout.write(f"Choose [0-{len(options)}]: ")
    sys.stdout.flush()
    line = sys.stdin.readline().strip()

    try:
        choice = int(line)
    except ValueError:
        return None

    if choice == 0:
        return None
    if 1 <= choice <= len(options):
        return options[choice - 1]
    return None
