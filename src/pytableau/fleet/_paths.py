"""Shared discovery of supported workbook files for fleet operations."""

from pathlib import Path

DEFAULT_PATTERN = "**/*.twb*"


def workbook_paths(directory: Path, pattern: str = DEFAULT_PATTERN) -> list[Path]:
    """Find files matching *pattern*, excluding directories and other suffixes."""
    if not directory.is_dir():
        raise NotADirectoryError(f"Workbook directory does not exist: {directory}")
    return sorted(
        path
        for path in directory.glob(pattern)
        if path.is_file() and path.suffix.lower() in {".twb", ".twbx"}
    )
