# id3-correction

A command-line tool that synchronizes ID3 tags (title and track number) across multiple folders containing the same audio files.

## What it does

When you have the same album in multiple folders (e.g. from different sources) and the metadata has drifted over time, this tool detects inconsistencies, resolves them using majority voting, and applies corrections after user confirmation.

- Compares `title` and `track` tags across all copies of each file
- Determines the correct value by strict majority vote (>50%)
- Falls back to extracting track numbers from filenames or title matching when no tags exist
- Reports conflicts when no majority can be determined, and prompts for resolution
- Flags files missing from some folders and files with no tags anywhere

For full details, see [SPEC.md](SPEC.md).

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Dry-run (default) — show report only, make no changes
python -m id3_correction ./album_v1 ./album_v2 ./album_v3

# Apply majority-based corrections without prompting (fallback/conflict prompts still appear)
python -m id3_correction ./album_v1 ./album_v2 ./album_v3 --apply

# Show detailed per-file scan output before the report
python -m id3_correction ./album_v1 ./album_v2 --verbose
```

### Options

```
positional arguments:
  folder        Two or more folder paths to synchronize

options:
  --apply       Apply majority-based corrections without prompting
  --verbose     Show detailed per-file scan output
  --help        Show this help message
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (invalid arguments, missing folder, scan error) |
| 2 | Conflicts remain unresolved after apply phase |

## Running tests

```bash
python -m pytest
```
