from __future__ import annotations

import argparse
import sys
from pathlib import Path

from id3_correction.analyzer import analyze
from id3_correction.applier import apply_corrections_with_groups
from id3_correction.reporter import generate_report
from id3_correction.scanner import scan_folders


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="id3-correction",
        description=(
            "Synchronize ID3 tags (title and track number) across multiple "
            "folders containing the same audio files."
        ),
    )
    parser.add_argument(
        "folders",
        nargs="+",
        metavar="folder",
        help="Two or more folder paths to synchronize",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply majority-based corrections without prompting",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed per-file scan output",
    )

    args = parser.parse_args()

    # Validate: at least 2 folders
    if len(args.folders) < 2:
        print(
            "Error: at least 2 folder paths are required.",
            file=sys.stderr,
        )
        return 1

    # Validate: all folders must exist and be directories
    folder_paths: list[Path] = []
    for raw in args.folders:
        p = Path(raw).resolve()
        if not p.exists():
            print(f"Error: folder does not exist: {raw}", file=sys.stderr)
            return 1
        if not p.is_dir():
            print(f"Error: not a directory: {raw}", file=sys.stderr)
            return 1
        folder_paths.append(p)

    # Phase 1: Scan
    try:
        scan_result = scan_folders(folder_paths)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Verbose: per-file details
    if args.verbose:
        print("=== VERBOSE SCAN ===")
        for identity, group in sorted(scan_result.file_groups.items()):
            for rec in group.files:
                print(
                    f"  {rec.path}  identity={rec.identity!r}  "
                    f"title={rec.title!r}  track={rec.track!r}"
                )

    # Phase 2: Analyze
    analysis = analyze(scan_result, folder_paths)

    # Phase 3: Report
    report = generate_report(scan_result, analysis, folder_paths)
    print(report)

    # Nothing to do?
    if not analysis.corrections and not analysis.conflicts:
        print("\nEverything is in sync. Nothing to do.")
        return 0

    # Phase 4: Apply
    n_modified = apply_corrections_with_groups(
        analysis,
        scan_result.file_groups,
        auto_apply=args.apply,
    )
    print(f"\nDone. {n_modified} files modified.")

    # Exit code 2 if unresolved conflicts remain
    if analysis.conflicts:
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
