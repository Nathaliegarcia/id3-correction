# id3-correction — Specification

## Overview

A command-line tool that synchronizes ID3 tags (title and track number) across multiple folders containing the same audio files. The tool detects inconsistencies, resolves them using majority voting, and applies corrections after user confirmation.

## Problem

Multiple folders contain the same set of audio files (e.g. the same album from different sources). Over time, the metadata (ID3 tags) across these copies has drifted: some files are missing titles, some have wrong track numbers, some have no tags at all. Manual correction is tedious and error-prone.

## Scope

- **Tags managed**: title (`TIT2`) and track number (`TRCK`) only.
- **File formats**: MP3. Any non-MP3 audio file encountered produces a warning so we can evaluate support later.
- **Language**: Python 3. Single external dependency: `mutagen`.

---

## Concepts

### Folder set

The user provides a list of folder paths as input. Each folder is expected to contain roughly the same set of audio files. The tool processes all folders together as one unit of work.

### File identity

A file's **identity** is its filename without extension (e.g. `01 - River.mp3` → `01 - River`). Two files across different folders are considered "the same file" if they share the same identity.

### Canonical values

For each file identity present across folders, the tool collects all observed values for title and track number. The **canonical value** for a given tag is determined by strict majority: if more than 50% of the folders that contain this file agree on a value, that value is canonical.

If no strict majority exists, the value is an **unresolvable conflict** and requires user intervention.

### Track number resolution

Track number for a file is resolved in this order:

1. **From ID3 tags across folders** — collect track numbers from all copies of the file. If a strict majority exists, that's the canonical value.
2. **From filename (fallback)** — if the file has no track number in any folder, attempt to extract a leading number from the filename (e.g. `07 - River.mp3` → track 7). This fallback **requires user confirmation** before being accepted.
3. **From title matching (fallback)** — if the filename has no leading number, attempt to match the file's title against other files that DO have a track number. If a match is found, inherit the track number. This also **requires user confirmation**.

### Title resolution

Title for a file is resolved as follows:

1. **From ID3 tags across folders** — collect titles from all copies. Strict majority wins.
2. **From files with the same name in other folders** — if some copies have a title and some don't, the majority value (or the only known value) is used.

If a file has no title anywhere across all folders, it is flagged as **missing title** in the report.

---

## Behavior

### Phase 1: Scan

Read all folders. For every file:

- Verify it is an MP3. If not, emit a **warning** with the file path and format, then skip it.
- Read its ID3 tags (title, track number).
- Record its filename identity.

Group files by identity across folders.

### Phase 2: Analyze

For each file identity:

- Determine the canonical title (majority vote).
- Determine the canonical track number (majority vote, then fallback chain).
- Detect **conflicts**: cases where no strict majority exists.
- Detect **missing files**: a file identity that exists in some folders but not all.
- Detect **missing tags**: a file has no title or no track number in any folder.

### Phase 3: Report (dry-run)

Print a structured report:

```
=== SCAN SUMMARY ===
Folders: 5
Total files scanned: 120
File identities: 24

=== WARNINGS ===
[WARN] /path/folder3/song.flac — non-MP3 file, skipped

=== MISSING FILES ===
[MISSING] "05 - River" — not found in: /path/folder2

=== CONFLICTS (require resolution) ===
[CONFLICT] "03 - Mountain" — title:
  "Mountain"     in: folder1, folder2, folder4
  "The Mountain" in: folder3, folder5
  → No strict majority. User input required.

=== CORRECTIONS (to be applied) ===
[FIX] /path/folder3/03 - Mountain.mp3
  title: (empty) → "Mountain"
[FIX] /path/folder5/07 - River.mp3
  track: (empty) → 7  [source: filename]  ⚠ requires confirmation
[FIX] /path/folder1/River.mp3
  track: (empty) → 7  [source: title match from folder2]  ⚠ requires confirmation

=== TOTALS ===
Corrections to apply: 12
Conflicts to resolve: 1
Missing files flagged: 1
```

No files are modified in this phase. This is the default behavior.

### Phase 4: Apply

After the report is shown, the user is prompted to confirm:

- **For standard corrections** (majority-based): `Apply N corrections? [y/N]`
- **For fallback-sourced corrections** (filename/title-match): each is confirmed individually.
- **For conflicts**: the user is shown the options and asked to pick the correct value, or skip.

Corrections are then written to the actual MP3 files (in-place ID3 tag update via mutagen).

A `--apply` flag can be passed to skip the confirmation prompt for majority-based corrections (but fallback corrections and conflicts still prompt).

---

## CLI Interface

```
usage: id3-correction <folder1> <folder2> [folder3 ...] [options]

positional arguments:
  folders              Two or more folder paths to synchronize

options:
  --apply              Apply majority-based corrections without prompting
  --verbose            Show detailed per-file scan output
  --help               Show this help message
```

### Examples

```bash
# Dry-run (default) — show report only
python -m id3_correction ./album_v1 ./album_v2 ./album_v3

# Apply corrections with prompting for edge cases
python -m id3_correction ./album_v1 ./album_v2 ./album_v3 --apply
```

---

## File structure

```
id3-correction/
├── SPEC.md
├── README.md
├── requirements.txt          # mutagen
├── setup.py                  # or pyproject.toml — minimal packaging
├── id3_correction/
│   ├── __init__.py
│   ├── __main__.py           # CLI entry point (argparse)
│   ├── scanner.py            # Phase 1: read folders and extract tags
│   ├── analyzer.py           # Phase 2: majority voting, conflict detection
│   ├── reporter.py           # Phase 3: format and print the report
│   ├── applier.py            # Phase 4: write corrections to files
│   └── models.py             # Data classes (FileRecord, Correction, Conflict, etc.)
└── tests/
    ├── __init__.py
    ├── test_scanner.py
    ├── test_analyzer.py
    ├── test_reporter.py
    └── test_applier.py
```

---

## Data model

### FileRecord

Represents one MP3 file as scanned from disk.

| Field      | Type         | Description                          |
|------------|--------------|--------------------------------------|
| path       | Path         | Absolute path to the file            |
| folder     | Path         | Which input folder this belongs to   |
| identity   | str          | Filename without extension           |
| title      | str \| None  | ID3 title tag, or None if absent     |
| track      | int \| None  | ID3 track number, or None if absent  |

### FileGroup

All copies of a single file identity across folders.

| Field      | Type              | Description                              |
|------------|-------------------|------------------------------------------|
| identity   | str               | The shared filename identity              |
| files      | list[FileRecord]  | All files with this identity              |

### Correction

A planned tag modification.

| Field       | Type        | Description                                    |
|-------------|-------------|------------------------------------------------|
| file        | FileRecord  | The file to modify                             |
| tag         | str         | Which tag ("title" or "track")                 |
| old_value   | str \| None | Current value                                  |
| new_value   | str \| int  | Value to write                                 |
| source      | str         | How the value was determined: "majority", "filename", "title_match" |
| auto_apply  | bool        | True if majority-based (no confirmation needed with --apply) |

### Conflict

An unresolvable disagreement between folders.

| Field      | Type                       | Description                              |
|------------|----------------------------|------------------------------------------|
| identity   | str                        | The file identity                        |
| tag        | str                        | Which tag is conflicting                 |
| values     | dict[str, list[str]]       | value → list of folder names             |

### MissingFile

A file identity not present in all folders.

| Field           | Type       | Description                              |
|-----------------|------------|------------------------------------------|
| identity        | str        | The file identity                        |
| missing_from    | list[Path] | Folders where the file is absent         |

---

## Edge cases

| Situation | Behavior |
|-----------|----------|
| Only 2 folders, they disagree (1 vs 1) | No majority → conflict, prompt user |
| File exists in only 1 folder | No comparison possible, skip (but flag as missing from others) |
| Track number tag is "3/12" format | Parse the first number (3) as track number |
| Title tag exists but is empty string | Treat as absent (None) |
| Filename has no extension | Use full filename as identity |
| Two files in same folder with same identity | Error — this shouldn't happen, abort with message |
| Folder is empty | Warning, proceed with remaining folders |
| Non-MP3 file | Warning with path, skip |

---

## Not in scope

- Modifying any tag other than title and track number.
- Renaming files.
- Copying or moving files between folders.
- Audio fingerprinting or content-based matching.
- Album art synchronization.
- Support for non-MP3 formats (flagged for future consideration via warnings).
