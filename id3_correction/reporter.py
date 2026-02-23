from __future__ import annotations

from pathlib import Path

from id3_correction.models import AnalysisResult, ScanResult


def generate_report(
    scan_result: ScanResult,
    analysis: AnalysisResult,
    all_folders: list[Path],
) -> str:
    """Return the full dry-run report as a string."""
    lines: list[str] = []

    # --- SCAN SUMMARY ---
    total_files = sum(
        len(group.files) for group in scan_result.file_groups.values()
    )
    lines.append("=== SCAN SUMMARY ===")
    lines.append(f"Folders: {len(all_folders)}")
    lines.append(f"Total files scanned: {total_files}")
    lines.append(f"File identities: {len(scan_result.file_groups)}")

    # --- WARNINGS ---
    if scan_result.warnings:
        lines.append("")
        lines.append("=== WARNINGS ===")
        for w in scan_result.warnings:
            lines.append(w)

    # --- MISSING FILES ---
    if analysis.missing_files:
        lines.append("")
        lines.append("=== MISSING FILES ===")
        for mf in analysis.missing_files:
            folders_str = ", ".join(str(p) for p in mf.missing_from)
            lines.append(f'[MISSING] "{mf.identity}" — not found in: {folders_str}')

    # --- MISSING TAGS ---
    if analysis.missing_tags:
        lines.append("")
        lines.append("=== MISSING TAGS ===")
        for identity, tag in analysis.missing_tags:
            lines.append(f'[MISSING TAG] "{identity}" — no {tag} in any folder')

    # --- CONFLICTS ---
    if analysis.conflicts:
        lines.append("")
        lines.append("=== CONFLICTS (require resolution) ===")
        for conflict in analysis.conflicts:
            lines.append(f'[CONFLICT] "{conflict.identity}" — {conflict.tag}:')
            for value, folders in conflict.values.items():
                folders_str = ", ".join(folders)
                lines.append(f'  {_format_value_quoted(conflict.tag, value):<20} in: {folders_str}')
            lines.append("  → No strict majority. User input required.")

    # --- CORRECTIONS ---
    if analysis.corrections:
        lines.append("")
        lines.append("=== CORRECTIONS (to be applied) ===")
        for corr in analysis.corrections:
            lines.append(f"[FIX] {corr.file.path}")
            old_str = _format_value(corr.tag, corr.old_value)
            new_str = _format_value(corr.tag, corr.new_value)
            source_label = f"  [source: {corr.source}]" if corr.source != "majority" else ""
            confirm_marker = "  ⚠ requires confirmation" if not corr.auto_apply else ""
            lines.append(f"  {corr.tag}: {old_str} → {new_str}{source_label}{confirm_marker}")

    # --- TOTALS ---
    lines.append("")
    lines.append("=== TOTALS ===")
    lines.append(f"Corrections to apply: {len(analysis.corrections)}")
    lines.append(f"Conflicts to resolve: {len(analysis.conflicts)}")
    lines.append(f"Missing files flagged: {len(analysis.missing_files)}")

    return "\n".join(lines)


def _format_value(tag: str, value: str | int | None) -> str:
    """Format a tag value for display."""
    if value is None:
        return "(empty)"
    if tag == "title":
        return f'"{value}"'
    # track number — plain
    return str(value)


def _format_value_quoted(tag: str, value: str) -> str:
    """Format a value for the conflict section."""
    if tag == "title":
        return f'"{value}"'
    return str(value)
