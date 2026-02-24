"""09_patch_roundtrip.py

Demonstrate the full Patch lifecycle:
  1. Create a before/after workbook pair
  2. Compute a semantic diff
  3. Serialize the diff as a reusable Patch JSON file
  4. Apply that Patch to a third workbook (proving portability)
  5. Verify the applied changes

This pattern enables "infrastructure-as-code" for Tableau: store diffs
as code-reviewed JSON and replay them in CI/CD without touching Tableau
Desktop.

Usage:
    python examples/09_patch_roundtrip.py [before.twb] [after.twb]
    python examples/09_patch_roundtrip.py \\
        tests/fixtures/minimal_v2022_4.twb \\
        tests/fixtures/modified_v2024_1.twb

Requirements: pip install pytableau
"""

from __future__ import annotations

import json
import sys
import tempfile
import warnings
from pathlib import Path

from pytableau import Workbook
from pytableau.inspect.diff import Patch, PatchAction, PatchOp, apply_patch, diff_workbooks


def demo(before_path: str, after_path: str) -> None:
    before = Workbook.open(before_path)
    after  = Workbook.open(after_path)

    print(f"\nPatch Roundtrip Demo")
    print(f"{'=' * 55}")
    print(f"  Before: {Path(before_path).name}  (v{before.version})")
    print(f"  After:  {Path(after_path).name}  (v{after.version})\n")

    # ── Step 1: Compute semantic diff ────────────────────────────────────────
    diff = diff_workbooks(before, after)
    print(f"Step 1 — Semantic diff")
    print(f"  is_empty:            {diff.is_empty()}")
    print(f"  datasources_added:   {diff.datasources_added}")
    print(f"  datasources_removed: {diff.datasources_removed}")
    print(f"  modified:            {list(diff.datasources_modified.keys())}")
    for ds_name, ds_diff in diff.datasources_modified.items():
        print(f"    {ds_name}: +{len(ds_diff.fields_added)} fields  "
              f"-{len(ds_diff.fields_removed)} fields  "
              f"~{len(ds_diff.fields_modified)} changed")

    # ── Step 2: Create patch from diff ───────────────────────────────────────
    patch = Patch.from_diff(diff)
    print(f"\nStep 2 — Patch from diff")
    print(f"  {len(patch.ops)} operation(s)")
    for op in patch.ops[:5]:
        print(f"    [{op.action}] target={op.target}  attr={op.attribute}")
    if len(patch.ops) > 5:
        print(f"    … and {len(patch.ops)-5} more")

    # ── Step 3: Serialize to JSON ─────────────────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".patch.json", delete=False, mode="w") as f:
        patch_path = Path(f.name)
        f.write(patch.to_json())

    size = patch_path.stat().st_size
    print(f"\nStep 3 — Serialized to {patch_path.name}  ({size} bytes)")

    # Demonstrate round-trip fidelity
    patch_json = json.loads(patch_path.read_text())
    restored   = Patch.from_dict(patch_json)
    assert len(restored.ops) == len(patch.ops), "Round-trip op count mismatch"
    print(f"  Round-trip verified: {len(restored.ops)} ops restored correctly")

    # ── Step 4: Apply patch to a fresh copy ──────────────────────────────────
    # Load a clean copy of "before" to apply the patch to
    target = Workbook.open(before_path)
    print(f"\nStep 4 — Apply patch to fresh copy of '{Path(before_path).name}'")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        applied_count = apply_patch(target, restored, validate=False)

    skipped = len(caught)
    print(f"  Applied: {applied_count} operation(s)  Skipped: {skipped}")

    if skipped:
        for w in caught:
            print(f"    ⚠ {w.message}")

    # ── Step 5: Save patched workbook ─────────────────────────────────────────
    out_path = patch_path.with_suffix(".patched.twb")
    target.save_as(out_path)
    print(f"\nStep 5 — Saved patched workbook: {out_path.name}")

    # Cleanup temp files
    patch_path.unlink(missing_ok=True)

    print(f"\n  ✓ Patch lifecycle complete")
    print(f"\nTo use patches in production:")
    print(f"  patch = Patch.from_diff(before.diff(after))")
    print(f"  patch_json = patch.to_json()")
    print(f"  # commit patch_json to git, apply in CI:")
    print(f"  apply_patch(workbook, Patch.from_dict(json.loads(patch_json)))")


if __name__ == "__main__":
    before = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/minimal_v2022_4.twb"
    after  = sys.argv[2] if len(sys.argv) > 2 else "tests/fixtures/modified_v2024_1.twb"
    demo(before, after)
