"""05_canonical_snapshot.py

Create a stable, version-control-friendly "snapshot" of a workbook alongside
the source file. The snapshot is:

  • <workbook>.canonical.json  — sorted, deterministic JSON representation
  • <workbook>.clean.twb       — thumbnail-stripped XML (git-diff-friendly)

Running this as a pre-commit hook eliminates noisy Tableau save-noise from
your git history (base64 thumbnails, session IDs, zoom levels).

Usage:
    python examples/05_canonical_snapshot.py <workbook> [<workbook2> ...]
    python examples/05_canonical_snapshot.py tests/fixtures/minimal_v2022_4.twb

    # As a git pre-commit hook:
    #   cp examples/05_canonical_snapshot.py .git/hooks/pre-commit-tableau
    #   chmod +x .git/hooks/pre-commit-tableau

Requirements: pip install pytableau
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pytableau import Workbook
from pytableau.xml.canonical import canonicalize, git_clean


def snapshot(path: Path) -> None:
    wb = Workbook.open(path)

    # 1. Canonical JSON sidecar
    canon = canonicalize(wb)
    json_path = path.with_suffix(".canonical.json")
    json_path.write_text(json.dumps(canon, indent=2, sort_keys=True), encoding="utf-8")
    print(f"  JSON snapshot → {json_path.name}  ({json_path.stat().st_size:,} bytes)")

    # 2. Clean TWB copy (thumbnails + volatile attrs stripped)
    if path.suffix == ".twb":
        clean_path = path.with_stem(path.stem + ".clean")
        clean_xml = git_clean(path, in_place=False)
        clean_path.write_text(clean_xml, encoding="utf-8")
        original_size = path.stat().st_size
        clean_size = clean_path.stat().st_size
        saved = original_size - clean_size
        pct = (saved / original_size * 100) if original_size else 0
        print(f"  Clean TWB     → {clean_path.name}  "
              f"({clean_size:,} bytes, saved {saved:,} bytes / {pct:.0f}%)")
    else:
        print(f"  (Skipping clean copy — not a .twb)")

    # 3. Quick content summary
    print(f"  Datasources:  {len(list(wb.datasources))}")
    print(f"  Worksheets:   {len(list(wb.worksheets))}")
    print(f"  Dashboards:   {len(list(wb.dashboards))}")

    total_calcs = sum(len(ds.calculated_fields) for ds in wb.datasources)
    print(f"  Calc fields:  {total_calcs}")


def main(paths: list[str]) -> None:
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"  ERROR: file not found: {p}")
            continue
        print(f"\nSnapshot: {path.name}")
        print(f"{'─' * 50}")
        snapshot(path)
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1:])
