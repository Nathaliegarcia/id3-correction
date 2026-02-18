from __future__ import annotations

from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError

from id3_correction.models import FileGroup, FileRecord, ScanResult


def scan_folders(folders: list[Path]) -> ScanResult:
    """Scan all given folders and extract ID3 tags from MP3 files."""
    file_groups: dict[str, FileGroup] = {}
    warnings: list[str] = []

    for folder in folders:
        files_in_folder = list(folder.iterdir()) if folder.is_dir() else []

        if not files_in_folder:
            warnings.append(f"[WARN] {folder} — folder is empty")
            continue

        # Track identities seen within this folder to detect duplicates
        seen_identities: dict[str, Path] = {}

        for file_path in sorted(files_in_folder):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() != ".mp3":
                warnings.append(
                    f"[WARN] {file_path} — non-MP3 file, skipped"
                )
                continue

            identity = _extract_identity(file_path.name)

            if identity in seen_identities:
                raise ValueError(
                    f"Duplicate identity '{identity}' in folder {folder}: "
                    f"{seen_identities[identity]} and {file_path}"
                )
            seen_identities[identity] = file_path

            title, track = _read_tags(file_path)

            record = FileRecord(
                path=file_path,
                folder=folder,
                identity=identity,
                title=title,
                track=track,
            )

            if identity not in file_groups:
                file_groups[identity] = FileGroup(identity=identity)
            file_groups[identity].files.append(record)

    return ScanResult(file_groups=file_groups, warnings=warnings)


def _read_tags(file_path: Path) -> tuple[str | None, int | None]:
    """Read TIT2 and TRCK tags from an MP3 file. Returns (title, track)."""
    try:
        tags = ID3(str(file_path))
    except ID3NoHeaderError:
        return None, None
    except Exception:
        return None, None

    # Title
    tit2 = tags.get("TIT2")
    title: str | None = None
    if tit2 is not None:
        raw_title = str(tit2)
        title = raw_title if raw_title else None

    # Track
    trck = tags.get("TRCK")
    track: int | None = None
    if trck is not None:
        track = _parse_track(str(trck))

    return title, track


def _parse_track(raw: str) -> int | None:
    """Parse a track number string. Handles 'N', 'N/M', empty, garbage."""
    if not raw or not raw.strip():
        return None
    # Handle "N/M" format — take the first number
    part = raw.strip().split("/")[0].strip()
    try:
        return int(part)
    except ValueError:
        return None


def _extract_identity(filename: str) -> str:
    """Return filename without extension. If no extension, return full filename."""
    p = Path(filename)
    if p.suffix:
        return p.stem
    return filename
