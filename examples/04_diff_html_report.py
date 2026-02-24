"""04_diff_html_report.py

Compare two versions of a workbook and generate a self-contained HTML
change report — useful for code review comments, release notes, or
audit trails before promoting to production.

Usage:
    python examples/04_diff_html_report.py <before> <after> [output.html]
    python examples/04_diff_html_report.py \\
        tests/fixtures/minimal_v2022_4.twb \\
        tests/fixtures/modified_v2024_1.twb \\
        diff_report.html

Requirements: pip install pytableau
"""

from __future__ import annotations

import sys
from pathlib import Path

from pytableau import Workbook
from pytableau.inspect.diff import diff_workbooks

_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 2rem; color: #1a1a2e; background: #f8f9fa; }
h1   { border-bottom: 3px solid #4a90e2; padding-bottom: .4rem; }
h2   { color: #4a90e2; margin-top: 2rem; }
.meta { color: #666; font-size: .9rem; margin-bottom: 1rem; }
.summary { display: flex; gap: 1.5rem; flex-wrap: wrap; margin: 1rem 0 2rem; }
.card { background: white; border-radius: 8px; padding: 1rem 1.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,.1); min-width: 120px; text-align: center; }
.card .num { font-size: 2rem; font-weight: 700; }
.card .lbl { font-size: .8rem; color: #666; text-transform: uppercase; letter-spacing: .05em; }
.added   .num { color: #2ecc71; }
.removed .num { color: #e74c3c; }
.changed .num { color: #f39c12; }
table  { border-collapse: collapse; width: 100%; background: white;
         border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
th     { background: #4a90e2; color: white; padding: .6rem 1rem; text-align: left; }
td     { padding: .5rem 1rem; border-bottom: 1px solid #eee; font-size: .9rem; }
tr:last-child td { border-bottom: none; }
.add { color: #2ecc71; font-weight: 600; }
.rem { color: #e74c3c; font-weight: 600; }
.chg { color: #f39c12; font-weight: 600; }
.empty { color: #aaa; font-style: italic; }
"""


def _rows(items: list[str], css_class: str, symbol: str) -> str:
    if not items:
        return f'<tr><td colspan="2" class="empty">none</td></tr>'
    return "".join(
        f'<tr><td class="{css_class}">{symbol}</td><td>{item}</td></tr>'
        for item in items
    )


def generate_html(before_path: str, after_path: str) -> str:
    before = Workbook.open(before_path)
    after  = Workbook.open(after_path)
    diff   = diff_workbooks(before, after)

    total_added   = len(diff.datasources_added) + len(diff.worksheets_added) + len(diff.dashboards_added)
    total_removed = len(diff.datasources_removed) + len(diff.worksheets_removed) + len(diff.dashboards_removed)
    total_changed = len(diff.datasources_modified)

    # Per-datasource field tables
    ds_tables = ""
    for ds_name, ds_diff in diff.datasources_modified.items():
        if ds_diff.is_empty():
            continue
        field_rows = (
            _rows(ds_diff.fields_added, "add", "+") +
            _rows(ds_diff.fields_removed, "rem", "−") +
            "".join(
                f'<tr><td class="chg">~</td>'
                f'<td><b>{fname}</b>: '
                + ", ".join(
                    f'{fd.attribute} <span style="color:#e74c3c">{fd.old_value}</span>'
                    f' → <span style="color:#2ecc71">{fd.new_value}</span>'
                    for fd in flist
                ) + "</td></tr>"
                for fname, flist in ds_diff.fields_modified.items()
            )
        )
        conn_rows = ""
        for c in ds_diff.connections_modified:
            conn_rows += (
                f'<tr><td class="chg">~</td>'
                f'<td>connection[{c["index"]}].{c["attribute"]}: '
                f'<span style="color:#e74c3c">{c["old"]}</span> → '
                f'<span style="color:#2ecc71">{c["new"]}</span></td></tr>'
            )

        ds_tables += f"""
        <h2>Datasource: {ds_name}</h2>
        <table>
          <tr><th>Change</th><th>Detail</th></tr>
          {field_rows}
          {conn_rows or ""}
        </table>
        """

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>pytableau diff report</title>
<style>{_CSS}</style>
</head><body>
<h1>Workbook Diff Report</h1>
<p class="meta">
  <b>Before:</b> {Path(before_path).name} (v{before.version}) &nbsp;→&nbsp;
  <b>After:</b>  {Path(after_path).name} (v{after.version})
</p>

<div class="summary">
  <div class="card added"><div class="num">{total_added}</div><div class="lbl">Added</div></div>
  <div class="card removed"><div class="num">{total_removed}</div><div class="lbl">Removed</div></div>
  <div class="card changed"><div class="num">{total_changed}</div><div class="lbl">Datasources changed</div></div>
</div>

<h2>Datasources</h2>
<table>
  <tr><th>Change</th><th>Name</th></tr>
  {_rows(diff.datasources_added, "add", "+")}
  {_rows(diff.datasources_removed, "rem", "−")}
</table>

<h2>Worksheets</h2>
<table>
  <tr><th>Change</th><th>Name</th></tr>
  {_rows(diff.worksheets_added, "add", "+")}
  {_rows(diff.worksheets_removed, "rem", "−")}
</table>

<h2>Dashboards</h2>
<table>
  <tr><th>Change</th><th>Name</th></tr>
  {_rows(diff.dashboards_added, "add", "+")}
  {_rows(diff.dashboards_removed, "rem", "−")}
</table>

{ds_tables}
</body></html>"""


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    before_path = sys.argv[1]
    after_path  = sys.argv[2]
    out_path    = sys.argv[3] if len(sys.argv) > 3 else "diff_report.html"

    html = generate_html(before_path, after_path)
    Path(out_path).write_text(html, encoding="utf-8")
    print(f"Report written to: {out_path}")
