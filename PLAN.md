# id3-correction — Implementation Plan

Each step must be fully completed (all acceptance criteria met, tests passing) before moving to the next. No step should introduce code that isn't tested.

---

## Step 1: Project scaffolding

Set up the project structure, dependency management, and test infrastructure.

**Work:**
- Create `id3_correction/` package directory with `__init__.py`
- Create `tests/` directory with `__init__.py`
- Create `requirements.txt` containing `mutagen`
- Create `pyproject.toml` with minimal project metadata (name, version, python requirement, mutagen dependency, entry point `id3-correction = "id3_correction.__main__:main"`)
- Create empty placeholder files for all modules: `models.py`, `scanner.py`, `analyzer.py`, `reporter.py`, `applier.py`, `__main__.py`
- Verify `pytest` runs and discovers the test directory (0 tests collected, no errors)

**Acceptance criteria:**
- [ ] `id3_correction/` exists with `__init__.py` and all placeholder modules
- [ ] `tests/` exists with `__init__.py`
- [ ] `requirements.txt` lists `mutagen`
- [ ] `pyproject.toml` is valid and declares the `id3-correction` entry point
- [ ] `python -m pytest` runs without errors (0 tests collected is fine)
- [ ] `python -m id3_correction` runs without crashing (can just print "not implemented" or exit cleanly)

---

## Step 2: Data models

Implement all data classes used throughout the project. These are the shared vocabulary between all modules.

**Work:**
- In `models.py`, implement the following dataclasses:
  - `FileRecord(path: Path, folder: Path, identity: str, title: str | None, track: int | None)`
  - `FileGroup(identity: str, files: list[FileRecord])`
  - `Correction(file: FileRecord, tag: str, old_value: str | int | None, new_value: str | int, source: str, auto_apply: bool)`
    - `source` must be one of: `"majority"`, `"filename"`, `"title_match"`
    - `auto_apply` is `True` only when `source == "majority"`
  - `Conflict(identity: str, tag: str, values: dict[str, list[str]])`
    - `values` maps each observed value (as string) to a list of folder names that have it
  - `MissingFile(identity: str, missing_from: list[Path])`
  - `AnalysisResult(corrections: list[Correction], conflicts: list[Conflict], missing_files: list[MissingFile], missing_tags: list[tuple[str, str]])`
    - `missing_tags` is a list of `(identity, tag_name)` for files with no value in any folder
  - `ScanResult(file_groups: dict[str, FileGroup], warnings: list[str])`
- Write unit tests in `test_models.py`:
  - Test construction of each dataclass with valid data
  - Test that `auto_apply` is consistent with `source` (document this as a convention, not enforced by the class — the test just validates expected usage)
  - Test that `FileGroup` correctly holds multiple `FileRecord` entries

**Acceptance criteria:**
- [ ] All dataclasses are defined in `models.py` with correct type annotations
- [ ] No logic in models — they are pure data containers
- [ ] All fields match the types specified in `SPEC.md` data model section
- [ ] `ScanResult` and `AnalysisResult` aggregate types exist for passing data between phases
- [ ] `test_models.py` passes with all tests green
- [ ] `python -m pytest` — all tests pass

---

## Step 3: Scanner (Phase 1)

Implement folder scanning and ID3 tag extraction.

**Work:**
- In `scanner.py`, implement:
  - `scan_folders(folders: list[Path]) -> ScanResult`
    - Iterates each folder, lists all files
    - For each file:
      - If not `.mp3` extension (case-insensitive): add a warning string to warnings list, skip
      - If `.mp3`: read ID3 tags using mutagen
        - Extract title from `TIT2` frame. If missing or empty string → `None`
        - Extract track from `TRCK` frame. If present, parse it (handle `"3/12"` format → `3`). If missing or empty → `None`
        - Compute identity: filename stem (without extension)
      - Create `FileRecord` and add to the appropriate `FileGroup`
    - After scanning all folders, check for duplicate identities within the same folder. If found, raise a clear error with the folder path and duplicated identity
    - Return `ScanResult`
  - `_parse_track(raw: str) -> int | None` (private helper)
    - Handles: `"3"` → `3`, `"3/12"` → `3`, `""` → `None`, non-numeric → `None`
  - `_extract_identity(filename: str) -> str` (private helper)
    - Returns filename without extension. If no extension, returns full filename.
- Write unit tests in `test_scanner.py`:
  - Create temporary MP3 files with mutagen for testing (use `mutagen.mp3.MP3` and add `TIT2`/`TRCK` frames)
  - Test: MP3 with both title and track → correctly extracted
  - Test: MP3 with missing title → `title` is `None`
  - Test: MP3 with missing track → `track` is `None`
  - Test: MP3 with no ID3 tags at all → both `None`
  - Test: MP3 with track in `"3/12"` format → parsed as `3`
  - Test: MP3 with empty string title → treated as `None`
  - Test: non-MP3 file in folder → warning emitted, file skipped
  - Test: file grouping — same filename in 2 folders → single `FileGroup` with 2 records
  - Test: duplicate identity in same folder → raises error
  - Test: empty folder → warning, no crash
  - Test: identity extraction — `"song.mp3"` → `"song"`, `"song"` → `"song"`, `"my.song.mp3"` → `"my.song"`

**Acceptance criteria:**
- [ ] `scan_folders()` reads all `.mp3` files from all provided folders
- [ ] Non-MP3 files produce a warning containing the file path and are skipped
- [ ] ID3 title (`TIT2`) is extracted; empty string treated as `None`
- [ ] ID3 track (`TRCK`) is extracted; `"N/M"` format handled; empty treated as `None`
- [ ] Files are grouped by identity (filename stem) across folders
- [ ] Duplicate identity within one folder raises a clear error
- [ ] Empty folders produce a warning, don't crash
- [ ] `_parse_track` handles all edge cases: int string, `N/M`, empty, garbage
- [ ] All tests in `test_scanner.py` pass
- [ ] `python -m pytest` — all tests pass

---

## Step 4: Analyzer — majority voting (Phase 2, core)

Implement the core analysis logic: majority voting for title and track.

**Work:**
- In `analyzer.py`, implement:
  - `analyze(scan_result: ScanResult, all_folders: list[Path]) -> AnalysisResult`
    - For each `FileGroup` in `scan_result.file_groups`:
      - Call `_resolve_title(group, all_folders)` and `_resolve_track(group, all_folders)`
      - Collect corrections, conflicts, missing files, missing tags
    - Return `AnalysisResult`
  - `_resolve_title(group: FileGroup, all_folders: list[Path]) -> tuple[list[Correction], list[Conflict], list[tuple[str, str]]]`
    - Collect all non-None titles from the group's files
    - If no titles exist anywhere → add `(identity, "title")` to missing_tags, return
    - Count occurrences of each title value
    - If one value has strict majority (count > total_files_in_group / 2) → that's canonical
      - Generate `Correction` for every file that has a different or missing title
      - `source="majority"`, `auto_apply=True`
    - If no strict majority → create a `Conflict`
  - `_resolve_track(group: FileGroup, all_folders: list[Path]) -> tuple[list[Correction], list[Conflict], list[tuple[str, str]]]`
    - Collect all non-None track numbers from the group's files
    - **If tracks exist in some files**: count occurrences, apply majority rule same as title
    - **If no tracks exist anywhere** (all None): attempt fallback (Step 5)
    - If conflicting tracks with no majority → create a `Conflict`
  - `_strict_majority(values: list[T], total: int) -> T | None` (private helper)
    - Returns the value that appears more than `total / 2` times, or `None`
  - `_detect_missing_files(group: FileGroup, all_folders: list[Path]) -> MissingFile | None`
    - Compare folders that have this file vs `all_folders`
    - If some folders are missing → return `MissingFile`
- Write unit tests in `test_analyzer.py`:
  - Test: 3 folders, all have same title → no corrections, no conflicts
  - Test: 3 folders, 2 agree on title, 1 disagrees → 1 correction for the odd one out
  - Test: 3 folders, 2 have title, 1 has `None` → 1 correction to fill in the missing one
  - Test: 2 folders, different titles → conflict (no majority)
  - Test: 5 folders, 3 agree vs 2 disagree → majority wins, 2 corrections
  - Test: all files missing title → missing_tag entry, no corrections
  - Test: same tests for track number
  - Test: majority helper with various distributions
  - Test: missing file detection — file in 3 of 5 folders → `MissingFile` lists the 2 missing ones
  - Test: file in only 1 folder → `MissingFile` lists all other folders

**Acceptance criteria:**
- [ ] `analyze()` processes all file groups and returns a complete `AnalysisResult`
- [ ] Title resolution uses strict majority (> 50% of files in group)
- [ ] Track resolution uses strict majority (> 50% of files in group)
- [ ] Corrections are generated for every file that differs from canonical value
- [ ] Corrections have `source="majority"` and `auto_apply=True`
- [ ] Conflicts are generated when no strict majority exists
- [ ] Conflict `values` dict correctly maps each value to its folder names
- [ ] Missing files are detected by comparing present folders to all input folders
- [ ] Missing tags are flagged when no file in the group has a value
- [ ] All tests in `test_analyzer.py` pass
- [ ] `python -m pytest` — all tests pass

---

## Step 5: Analyzer — fallback track resolution

Implement the two fallback strategies for track number when no folder has a track tag.

**Work:**
- In `analyzer.py`, extend `_resolve_track`:
  - When **all** files in the group have `track=None`:
    1. **Filename fallback**: call `_track_from_filename(identity: str) -> int | None`
       - Use regex to check if the identity starts with a number: `re.match(r'^(\d+)', identity)`
       - If match → return the number as int
       - Otherwise → return `None`
    2. **Title-match fallback**: call `_track_from_title_match(group: FileGroup, all_groups: dict[str, FileGroup]) -> int | None`
       - Get the canonical title for this group (majority title, or the only known title)
       - Search all OTHER file groups for one whose canonical title matches AND has a resolved track number
       - If found → return that track number
       - Otherwise → return `None`
    3. If a fallback produces a value:
       - Generate `Correction` for every file in the group
       - `source="filename"` or `source="title_match"` accordingly
       - `auto_apply=False` (requires user confirmation)
  - The `analyze()` function must pass `scan_result.file_groups` to `_track_from_title_match` so it can cross-reference other groups
- Update unit tests in `test_analyzer.py`:
  - Test: filename `"07 - River"` with no track anywhere → correction with `source="filename"`, value `7`
  - Test: filename `"River"` (no number) with title `"River"`, another group `"07 - River"` has title `"River"` and track `7` → correction with `source="title_match"`, value `7`
  - Test: filename `"River"` with no number AND no title match → no correction, flagged as missing_tag
  - Test: filename `"12something"` → track 12 (leading digits only)
  - Test: filename `"song2you"` → track 2? No — this is ambiguous. Only match if the number is followed by a non-alphanumeric character or is the entire start. Refine regex to: `r'^(\d+)(?:\s*[-_.\s]|$)'` — number at start, followed by separator or end
  - Test: all fallback corrections have `auto_apply=False`

**Acceptance criteria:**
- [ ] Filename fallback extracts leading number only when followed by a separator or end of string
- [ ] Filename fallback regex does NOT match `"song2you"` → no false positives
- [ ] Filename fallback regex DOES match: `"07 - River"` → 7, `"12.Song"` → 12, `"3"` → 3, `"03_title"` → 3
- [ ] Title-match fallback finds track from another group that shares the same canonical title
- [ ] Title-match only activates when filename fallback fails
- [ ] All fallback corrections have `source` set correctly (`"filename"` or `"title_match"`)
- [ ] All fallback corrections have `auto_apply=False`
- [ ] When neither fallback works, the tag is flagged as missing (no incorrect correction generated)
- [ ] All tests pass
- [ ] `python -m pytest` — all tests pass

---

## Step 6: Reporter (Phase 3)

Implement the dry-run report output.

**Work:**
- In `reporter.py`, implement:
  - `generate_report(scan_result: ScanResult, analysis: AnalysisResult, all_folders: list[Path]) -> str`
    - Returns the full report as a string (not printed — the caller decides where to send it)
    - Sections, in order:
      1. **SCAN SUMMARY**: folder count, total MP3 files scanned, file identity count
      2. **WARNINGS**: non-MP3 file warnings from `scan_result.warnings` (skip section if none)
      3. **MISSING FILES**: from `analysis.missing_files` (skip section if none)
      4. **MISSING TAGS**: from `analysis.missing_tags` — files with no title or track anywhere (skip section if none)
      5. **CONFLICTS**: from `analysis.conflicts` — show each value and which folders have it (skip section if none)
      6. **CORRECTIONS**: from `analysis.corrections` — show file path, tag, old→new, source, confirmation marker (skip section if none)
      7. **TOTALS**: corrections count, conflicts count, missing files count
    - Format must match the examples in `SPEC.md`
    - Sections with zero items are omitted entirely (no empty headings)
  - `_format_value(value: str | int | None) -> str` (private helper)
    - `None` → `"(empty)"`, otherwise the value as string (quoted for titles, plain for track numbers)
- Write unit tests in `test_reporter.py`:
  - Test: report with only corrections → SUMMARY + CORRECTIONS + TOTALS sections present
  - Test: report with everything (warnings, missing, conflicts, corrections) → all sections present in correct order
  - Test: report with nothing to report → SUMMARY + TOTALS only (totals are all 0)
  - Test: correction formatting — old value `None` → `"(empty)"`, string values quoted, track numbers not quoted
  - Test: conflict formatting — each value listed with its folders
  - Test: fallback corrections show source label and confirmation marker
  - Test: section omission — no warnings → no WARNINGS section header in output

**Acceptance criteria:**
- [ ] `generate_report()` returns a complete string, does not print directly
- [ ] Report matches the format shown in `SPEC.md`
- [ ] Sections with zero items are omitted entirely
- [ ] Corrections show: file path, tag name, old→new values, source label, confirmation marker for non-majority
- [ ] Conflicts show: each competing value and which folders hold it
- [ ] Missing files show: identity and which folders lack it
- [ ] Totals section always present with correct counts
- [ ] All tests pass
- [ ] `python -m pytest` — all tests pass

---

## Step 7: Applier (Phase 4)

Implement the logic that writes corrections to MP3 files and handles user prompts.

**Work:**
- In `applier.py`, implement:
  - `apply_corrections(analysis: AnalysisResult, auto_apply: bool) -> int`
    - Returns the number of files actually modified
    - **Majority corrections** (`auto_apply=True` on correction):
      - If `auto_apply` CLI flag is set → apply without prompting
      - Otherwise → prompt once: `Apply N majority-based corrections? [y/N]`
    - **Fallback corrections** (`auto_apply=False` on correction):
      - Always prompt individually: `Set track of "/path/file.mp3" to 7 [source: filename]? [y/N]`
    - **Conflicts**:
      - For each conflict, display the options and ask user to pick one (numbered list) or skip
      - If user picks a value → generate and apply corrections for all files that differ
    - After all prompts resolved, write tags:
      - Call `_write_tag(file_path: Path, tag: str, value: str | int)`
  - `_write_tag(file_path: Path, tag: str, value: str | int)`
    - Open the MP3 with mutagen
    - If `tag == "title"`: set `TIT2` frame
    - If `tag == "track"`: set `TRCK` frame (as string, just the number)
    - Save the file
  - `_prompt_yes_no(message: str) -> bool` (private helper)
    - Read from stdin, return True for `y`/`Y`, False otherwise
  - `_prompt_choice(conflict: Conflict) -> str | None` (private helper)
    - Display numbered options + "skip", return chosen value or `None`
- Write unit tests in `test_applier.py`:
  - Test: `_write_tag` correctly writes title to an MP3 file (verify with mutagen read-back)
  - Test: `_write_tag` correctly writes track number to an MP3 file
  - Test: `_write_tag` on a file with no existing ID3 tags (mutagen should create them)
  - Test: `apply_corrections` with `auto_apply=True` and only majority corrections → all applied, no prompts (mock stdin to verify no reads)
  - Test: `apply_corrections` with `auto_apply=False` and majority corrections → prompts once (mock stdin with "y", verify applied)
  - Test: `apply_corrections` with fallback corrections → each prompted individually (mock stdin)
  - Test: conflict resolution → mock stdin with a choice, verify correct tag written
  - Test: conflict skip → mock stdin with "skip", verify no writes

**Acceptance criteria:**
- [ ] `_write_tag` correctly modifies ID3 title in-place using mutagen
- [ ] `_write_tag` correctly modifies ID3 track number in-place using mutagen
- [ ] `_write_tag` handles files with no existing ID3 tags (creates tags)
- [ ] Majority corrections respect the `auto_apply` flag — no prompt when flag is set
- [ ] Without `auto_apply`, majority corrections are prompted as a batch (single y/N)
- [ ] Fallback corrections are always prompted individually regardless of flag
- [ ] Conflicts are presented as a numbered choice + skip option
- [ ] User can skip a conflict without any writes
- [ ] `apply_corrections` returns the correct count of modified files
- [ ] All prompts read from stdin (testable via mock)
- [ ] All tests pass
- [ ] `python -m pytest` — all tests pass

---

## Step 8: CLI entry point

Wire everything together in `__main__.py`.

**Work:**
- In `__main__.py`, implement:
  - `main()` function:
    - Parse arguments with `argparse`:
      - `folders`: positional, `nargs='+'`, at least 2 required (validate and error if < 2)
      - `--apply`: store_true
      - `--verbose`: store_true
    - Validate all folder paths exist and are directories
    - Call `scan_folders(folders)` → get `ScanResult`
    - If `--verbose`: print per-file scan details (file path, identity, title, track for each file)
    - Call `analyze(scan_result, folders)` → get `AnalysisResult`
    - Call `generate_report(scan_result, analysis, folders)` → print the report
    - If there are corrections or conflicts:
      - Call `apply_corrections(analysis, auto_apply=args.apply)`
      - Print final summary: `"Done. N files modified."`
    - If nothing to do: print `"Everything is in sync. Nothing to do."`
  - Exit codes:
    - `0`: success (whether or not changes were made)
    - `1`: error (invalid args, scanning error, write failure)
    - `2`: conflicts remain unresolved (user skipped them)
- Write integration tests (can be in `test_main.py` or `test_integration.py`):
  - Test: create 3 temp folders with MP3 files, some with mismatched tags, run the full pipeline, verify report output contains expected sections
  - Test: less than 2 folders → exit code 1 with error message
  - Test: non-existent folder → exit code 1 with error message
  - Test: all files in sync → "Nothing to do" message
  - Test: `--apply` flag with majority corrections → files are modified (verify with mutagen read-back)

**Acceptance criteria:**
- [ ] `python -m id3_correction folder1 folder2` runs the full scan → analyze → report pipeline
- [ ] Fewer than 2 folders → clear error message, exit code 1
- [ ] Non-existent folder → clear error message, exit code 1
- [ ] `--apply` flag triggers automatic application of majority-based corrections
- [ ] `--verbose` flag shows per-file scan details before the report
- [ ] Exit code 0 on success, 1 on error, 2 on unresolved conflicts
- [ ] Report is printed to stdout
- [ ] Errors are printed to stderr
- [ ] All tests pass
- [ ] `python -m pytest` — all tests pass

---

## Step 9: End-to-end testing

Build a comprehensive integration test that exercises the entire tool as a user would.

**Work:**
- Create `tests/test_e2e.py` with realistic scenarios:
  - **Scenario A — clean sync**: 3 folders, identical files, identical tags → "Nothing to do"
  - **Scenario B — missing title**: 3 folders, file in folder3 has no title, folders 1&2 agree → correction proposed for folder3
  - **Scenario C — missing track, filename fallback**: all 3 folders have file `"05 - River.mp3"` with no track tag → fallback proposes track 5 from filename
  - **Scenario D — missing track, title-match fallback**: file `"River.mp3"` (no number) has title "River" in all folders but no track; file `"05 - River.mp3"` in all folders has track 5 and title "River" → title-match proposes track 5
  - **Scenario E — conflict**: 2 folders say title is "Mountain", 2 say "The Mountain" → conflict reported
  - **Scenario F — missing file**: file exists in folders 1&2 but not folder 3 → flagged
  - **Scenario G — non-MP3**: one folder contains a `.flac` file → warning emitted
  - **Scenario H — full apply**: set up mismatched tags, run with `--apply` and mock stdin, verify files are actually corrected (read back with mutagen)
- Each scenario:
  - Sets up temp folders with specific MP3 files using a test helper
  - Runs the pipeline (can call `main()` directly or use subprocess)
  - Asserts specific strings in the report output
  - For apply scenarios: reads back the MP3 tags and asserts correctness

**Acceptance criteria:**
- [ ] All 8 scenarios pass
- [ ] Scenario H verifies actual file modification (not just report output)
- [ ] Test helper creates valid MP3 files that mutagen can read/write (not empty files)
- [ ] No test leaks files outside temp directories
- [ ] `python -m pytest` — all tests pass
- [ ] `python -m pytest --tb=short` shows 0 failures

---

## Step 10: README and final polish

Write user-facing documentation and verify the tool works end-to-end from a clean install.

**Work:**
- Update `README.md` with:
  - One-line description
  - Install instructions: `pip install -r requirements.txt`
  - Usage examples (same as SPEC.md CLI section)
  - What the tool does (brief, reference SPEC.md for details)
- Verify from scratch:
  - `pip install -r requirements.txt` in a clean venv
  - `python -m id3_correction --help` shows usage
  - Run against sample folders (manual or test fixtures)
  - `python -m pytest` — all green
- Clean up any dead code, unused imports, or TODOs left in the codebase

**Acceptance criteria:**
- [ ] `README.md` has install instructions, usage examples, and a description
- [ ] `pip install -r requirements.txt` installs cleanly (only mutagen)
- [ ] `python -m id3_correction --help` prints the help message
- [ ] `python -m pytest` — all tests pass, 0 warnings about the project code
- [ ] No TODOs, no dead code, no unused imports in any module
- [ ] Every module has its corresponding test file with meaningful coverage
