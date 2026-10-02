"""WorkbookDiff: semantic diff and patch system for Tableau workbooks.

Provides object-model level diffing (not raw XML text) so diffs describe
*what changed* in terms of datasources, fields, connections, worksheets,
and dashboards — not XML attribute reordering.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from enum import Enum
from html import escape as _html_escape
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


# ---------------------------------------------------------------------------
# Diff data structures
# ---------------------------------------------------------------------------


@dataclass
class FieldDiff:
    """Single attribute change on a field."""

    attribute: str
    old_value: str | None
    new_value: str | None


@dataclass
class DatasourceDiff:
    """All changes within a single datasource."""

    name: str
    fields_added: list[str] = field(default_factory=list)
    fields_removed: list[str] = field(default_factory=list)
    fields_modified: dict[str, list[FieldDiff]] = field(default_factory=dict)
    connections_modified: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            not self.fields_added
            and not self.fields_removed
            and not self.fields_modified
            and not self.connections_modified
        )


@dataclass
class WorkbookDiff:
    """Semantic diff between two Tableau workbooks."""

    before_version: str
    after_version: str
    datasources_added: list[str] = field(default_factory=list)
    datasources_removed: list[str] = field(default_factory=list)
    datasources_modified: dict[str, DatasourceDiff] = field(default_factory=dict)
    worksheets_added: list[str] = field(default_factory=list)
    worksheets_removed: list[str] = field(default_factory=list)
    dashboards_added: list[str] = field(default_factory=list)
    dashboards_removed: list[str] = field(default_factory=list)

    components_modified: dict[str, list[str]] = field(default_factory=dict)
    assets_modified: list[str] = field(default_factory=list)
    before_state: dict[str, Any] | None = field(default=None, repr=False)
    after_state: dict[str, Any] | None = field(default=None, repr=False)

    def is_empty(self) -> bool:
        """Return ``True`` if there are no changes."""
        return (
            not self.components_modified
            and not self.assets_modified
            and not self.datasources_added
            and not self.datasources_removed
            and not self.datasources_modified
            and not self.worksheets_added
            and not self.worksheets_removed
            and not self.dashboards_added
            and not self.dashboards_removed
            and self.before_version == self.after_version
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "components_modified": self.components_modified,
            "assets_modified": self.assets_modified,
            "before_version": self.before_version,
            "after_version": self.after_version,
            "datasources_added": self.datasources_added,
            "datasources_removed": self.datasources_removed,
            "datasources_modified": {
                name: {
                    "fields_added": ds.fields_added,
                    "fields_removed": ds.fields_removed,
                    "fields_modified": {
                        caption: [
                            {"attribute": fd.attribute, "old": fd.old_value, "new": fd.new_value}
                            for fd in diffs
                        ]
                        for caption, diffs in ds.fields_modified.items()
                    },
                    "connections_modified": ds.connections_modified,
                }
                for name, ds in self.datasources_modified.items()
            },
            "worksheets_added": self.worksheets_added,
            "worksheets_removed": self.worksheets_removed,
            "dashboards_added": self.dashboards_added,
            "dashboards_removed": self.dashboards_removed,
        }

    def to_text(self) -> str:
        """Return a human-readable text summary of the diff."""
        lines: list[str] = []
        if self.before_version != self.after_version:
            lines.append(f"  version: {self.before_version!r} → {self.after_version!r}")
        for name in self.datasources_added:
            lines.append(f"+ datasource: {name}")
        for name in self.datasources_removed:
            lines.append(f"- datasource: {name}")
        for name, ds_diff in self.datasources_modified.items():
            lines.append(f"~ datasource: {name}")
            for f_name in ds_diff.fields_added:
                lines.append(f"  + field: {f_name}")
            for f_name in ds_diff.fields_removed:
                lines.append(f"  - field: {f_name}")
            for caption, diffs in ds_diff.fields_modified.items():
                for fd in diffs:
                    lines.append(
                        f"  ~ field {caption!r}.{fd.attribute}: {fd.old_value!r} → {fd.new_value!r}"
                    )
            for conn_change in ds_diff.connections_modified:
                lines.append(f"  ~ connection: {conn_change}")
        for name in self.worksheets_added:
            lines.append(f"+ worksheet: {name}")
        for name in self.worksheets_removed:
            lines.append(f"- worksheet: {name}")
        for name in self.dashboards_added:
            lines.append(f"+ dashboard: {name}")
        for name in self.dashboards_removed:
            lines.append(f"- dashboard: {name}")
        for category, names in self.components_modified.items():
            lines.extend(f"~ {category}: {name}" for name in names)
        lines.extend(f"~ asset: {name}" for name in self.assets_modified)
        if not lines:
            return "(no changes)"
        return "\n".join(lines)

    def to_html(self) -> str:
        """Return a basic HTML representation of the diff."""
        rows: list[str] = []

        def _row(sign: str, category: str, detail: str, color: str) -> str:
            return (
                f'<tr style="background:{color}">'
                f"<td>{_html_escape(sign)}</td>"
                f"<td>{_html_escape(category)}</td>"
                f"<td>{_html_escape(detail)}</td>"
                f"</tr>"
            )

        if self.before_version != self.after_version:
            rows.append(
                _row("~", "version", f"{self.before_version} → {self.after_version}", "#fffde7")
            )
        for name in self.datasources_added:
            rows.append(_row("+", "datasource", name, "#e8f5e9"))
        for name in self.datasources_removed:
            rows.append(_row("-", "datasource", name, "#ffebee"))
        for ds_name, ds_diff in self.datasources_modified.items():
            for f_name in ds_diff.fields_added:
                rows.append(_row("+", f"field ({ds_name})", f_name, "#e8f5e9"))
            for f_name in ds_diff.fields_removed:
                rows.append(_row("-", f"field ({ds_name})", f_name, "#ffebee"))
            for caption, diffs in ds_diff.fields_modified.items():
                for fd in diffs:
                    rows.append(
                        _row(
                            "~",
                            f"field ({ds_name})",
                            f"{caption}.{fd.attribute}: {fd.old_value!r} → {fd.new_value!r}",
                            "#fff3e0",
                        )
                    )
        for name in self.worksheets_added:
            rows.append(_row("+", "worksheet", name, "#e8f5e9"))
        for name in self.worksheets_removed:
            rows.append(_row("-", "worksheet", name, "#ffebee"))
        for name in self.dashboards_added:
            rows.append(_row("+", "dashboard", name, "#e8f5e9"))
        for name in self.dashboards_removed:
            rows.append(_row("-", "dashboard", name, "#ffebee"))

        for category, names in self.components_modified.items():
            rows.extend(_row("~", category, name, "#fff3e0") for name in names)
        rows.extend(_row("~", "asset", name, "#fff3e0") for name in self.assets_modified)
        if not rows:
            return "<p><em>(no changes)</em></p>"

        header = (
            "<table border='1' cellpadding='4'>"
            "<thead><tr><th></th><th>Category</th><th>Detail</th></tr></thead>"
            "<tbody>"
        )
        return header + "".join(rows) + "</tbody></table>"

    def to_changelog(self, *, version: str = "", date: str = "") -> str:
        """Return a Keep-a-Changelog-style Markdown entry for this diff.

        Example::

            diff = diff_workbooks(old_wb, new_wb)
            print(diff.to_changelog(version="1.2.0", date="2026-02-24"))
        """
        from datetime import date as _date

        ver_line = f"## [{version}]" if version else "## [Unreleased]"
        date_str = date or str(_date.today())
        header = f"{ver_line} — {date_str}\n"

        sections: dict[str, list[str]] = {
            "Added": [],
            "Changed": [],
            "Removed": [],
        }

        if self.before_version != self.after_version:
            sections["Changed"].append(
                f"Workbook source version: `{self.before_version}` → `{self.after_version}`"
            )

        for name in self.datasources_added:
            sections["Added"].append(f"Datasource `{name}`")
        for name in self.datasources_removed:
            sections["Removed"].append(f"Datasource `{name}`")
        for name, ds in self.datasources_modified.items():
            for f_name in ds.fields_added:
                sections["Added"].append(f"Field `{f_name}` in datasource `{name}`")
            for f_name in ds.fields_removed:
                sections["Removed"].append(f"Field `{f_name}` from datasource `{name}`")
            for caption, diffs in ds.fields_modified.items():
                for fd in diffs:
                    sections["Changed"].append(
                        f"Field `{caption}`.{fd.attribute}: "
                        f"`{fd.old_value}` → `{fd.new_value}` in `{name}`"
                    )
            for conn in ds.connections_modified:
                sections["Changed"].append(f"Connection in `{name}`: {conn}")

        for name in self.worksheets_added:
            sections["Added"].append(f"Worksheet `{name}`")
        for name in self.worksheets_removed:
            sections["Removed"].append(f"Worksheet `{name}`")
        for name in self.dashboards_added:
            sections["Added"].append(f"Dashboard `{name}`")
        for name in self.dashboards_removed:
            sections["Removed"].append(f"Dashboard `{name}`")

        for category, names in self.components_modified.items():
            sections["Changed"].extend(f"{category} `{name}`" for name in names)
        sections["Changed"].extend(f"Asset `{name}`" for name in self.assets_modified)
        if not any(sections.values()):
            return header + "\n_No changes._\n"

        body = ""
        for section, items in sections.items():
            if items:
                body += f"\n### {section}\n\n"
                body += "".join(f"- {item}\n" for item in items)
        return header + body


# ---------------------------------------------------------------------------
# diff_workbooks
# ---------------------------------------------------------------------------


def diff_workbooks(before: Workbook, after: Workbook) -> WorkbookDiff:
    """Compute a semantic diff between two workbooks.

    Compares datasource/field/connection/worksheet/dashboard structure.
    """
    diff = WorkbookDiff(
        before_version=before.version,
        after_version=after.version,
    )

    # --- Datasources ---
    before_ds_names = set(before.datasources.names)
    after_ds_names = set(after.datasources.names)
    diff.datasources_added = sorted(after_ds_names - before_ds_names)
    diff.datasources_removed = sorted(before_ds_names - after_ds_names)

    for name in sorted(before_ds_names & after_ds_names):
        b_ds = before.datasources[name]
        a_ds = after.datasources[name]
        ds_diff = _diff_datasource(name, b_ds, a_ds)
        if not ds_diff.is_empty():
            diff.datasources_modified[name] = ds_diff

    # --- Worksheets ---
    before_ws = set(before.worksheets.names)
    after_ws = set(after.worksheets.names)
    diff.worksheets_added = sorted(after_ws - before_ws)
    diff.worksheets_removed = sorted(before_ws - after_ws)

    # --- Dashboards ---
    before_db = set(before.dashboards.names)
    after_db = set(after.dashboards.names)
    diff.dashboards_added = sorted(after_db - before_db)
    diff.dashboards_removed = sorted(before_db - after_db)

    from lxml import etree

    from pytableau.core.state import snapshot, xml_identity

    diff.before_state, diff.after_state = snapshot(before), snapshot(after)
    for tag in ("datasource", "worksheet", "dashboard", "window", "style", "actions"):

        def index(wb: Workbook, tag: str = tag) -> dict[str, bytes]:
            container = wb.xml_root.find(tag + "s")
            nodes = list(container) if container is not None else wb.xml_root.findall(tag)
            return {
                n.get("name", str(i)): xml_identity(etree.tostring(n))
                for i, n in enumerate(nodes)
                if isinstance(n.tag, str)
            }

        left, right = index(before), index(after)
        changed = sorted(k for k in left.keys() & right.keys() if left[k] != right[k])
        if changed:
            diff.components_modified[tag] = changed
    if xml_identity(diff.before_state["xml"]) != xml_identity(diff.after_state["xml"]):
        # Full document coverage includes unknown extensions, parameters and root attributes.
        diff.components_modified["document"] = ["workbook"]
    left_assets, right_assets = diff.before_state["assets"], diff.after_state["assets"]
    if (diff.before_state["member"], diff.before_state["packaged"]) != (
        diff.after_state["member"],
        diff.after_state["packaged"],
    ):
        diff.components_modified["package"] = ["layout"]
    diff.assets_modified = sorted(
        k
        for k in left_assets.keys() | right_assets.keys()
        if left_assets.get(k) != right_assets.get(k)
    )
    return diff


def _diff_datasource(name: str, b_ds: Any, a_ds: Any) -> DatasourceDiff:
    ds_diff = DatasourceDiff(name=name)

    # Fields (all_fields includes calculated fields)
    b_fields = {f.caption: f for f in b_ds.all_fields}
    a_fields = {f.caption: f for f in a_ds.all_fields}
    ds_diff.fields_added = sorted(set(a_fields) - set(b_fields))
    ds_diff.fields_removed = sorted(set(b_fields) - set(a_fields))

    for caption in sorted(set(b_fields) & set(a_fields)):
        b_f = b_fields[caption]
        a_f = a_fields[caption]
        f_diffs = _diff_field(b_f, a_f)
        if f_diffs:
            ds_diff.fields_modified[caption] = f_diffs

    # Connections
    b_conns = list(b_ds.connections)
    a_conns = list(a_ds.connections)
    for idx, (b_c, a_c) in enumerate(zip(b_conns, a_conns, strict=False)):
        for attr in ("server", "dbname", "username", "class_"):
            b_val = getattr(b_c, attr, None)
            a_val = getattr(a_c, attr, None)
            if b_val != a_val:
                ds_diff.connections_modified.append(
                    {
                        "index": idx,
                        "attribute": attr.rstrip("_"),
                        "old": b_val,
                        "new": a_val,
                    }
                )

    return ds_diff


def _diff_field(b_f: Any, a_f: Any) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for attr in ("datatype", "role", "hidden"):
        b_val = str(getattr(b_f, attr, None))
        a_val = str(getattr(a_f, attr, None))
        if b_val != a_val:
            diffs.append(FieldDiff(attribute=attr, old_value=b_val, new_value=a_val))
    # Check formula for calculated fields
    b_formula = getattr(b_f, "formula", None)
    a_formula = getattr(a_f, "formula", None)
    if (b_formula is not None or a_formula is not None) and (b_formula or "") != (a_formula or ""):
        diffs.append(FieldDiff(attribute="formula", old_value=b_formula, new_value=a_formula))
    return diffs


# ---------------------------------------------------------------------------
# Patch system
# ---------------------------------------------------------------------------


class PatchAction(str, Enum):
    ADD_FIELD = "add_field"
    REMOVE_FIELD = "remove_field"
    MODIFY_FIELD = "modify_field"
    ADD_DATASOURCE = "add_datasource"
    REMOVE_DATASOURCE = "remove_datasource"
    MODIFY_CONNECTION = "modify_connection"
    ADD_WORKSHEET = "add_worksheet"
    REMOVE_WORKSHEET = "remove_worksheet"
    ADD_DASHBOARD = "add_dashboard"
    REMOVE_DASHBOARD = "remove_dashboard"


class PatchOp(NamedTuple):
    """A single atomic patch operation."""

    action: str
    target: str  # e.g. "datasource:sqlserver.sales/field:Sales"
    attribute: str | None
    old_value: Any
    new_value: Any


@dataclass
class Patch:
    """An ordered list of patch operations that can be applied to a workbook."""

    ops: list[PatchOp] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ops": [
                {
                    "action": op.action,
                    "target": op.target,
                    "attribute": op.attribute,
                    "old_value": op.old_value,
                    "new_value": op.new_value,
                }
                for op in self.ops
            ]
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Patch:
        ops = [
            PatchOp(
                action=o["action"],
                target=o["target"],
                attribute=o.get("attribute"),
                old_value=o.get("old_value"),
                new_value=o.get("new_value"),
            )
            for o in d.get("ops", [])
        ]
        return cls(ops=ops)

    @classmethod
    def from_diff(cls, diff: WorkbookDiff) -> Patch:
        """Convert a :class:`WorkbookDiff` into a :class:`Patch`."""
        if diff.before_state is not None and diff.after_state is not None:
            from pytableau.core.state import fingerprint

            return cls(
                []
                if diff.is_empty()
                else [
                    PatchOp(
                        "replace_snapshot",
                        "workbook",
                        None,
                        fingerprint(diff.before_state),
                        diff.after_state,
                    )
                ]
            )
        ops: list[PatchOp] = []

        if diff.before_version != diff.after_version:
            ops.append(
                PatchOp(
                    action=PatchAction.MODIFY_FIELD,
                    target="workbook",
                    attribute="version",
                    old_value=diff.before_version,
                    new_value=diff.after_version,
                )
            )

        for name in diff.datasources_added:
            ops.append(
                PatchOp(
                    action=PatchAction.ADD_DATASOURCE,
                    target=f"datasource:{name}",
                    attribute=None,
                    old_value=None,
                    new_value=name,
                )
            )
        for name in diff.datasources_removed:
            ops.append(
                PatchOp(
                    action=PatchAction.REMOVE_DATASOURCE,
                    target=f"datasource:{name}",
                    attribute=None,
                    old_value=name,
                    new_value=None,
                )
            )

        for ds_name, ds_diff in diff.datasources_modified.items():
            for caption in ds_diff.fields_added:
                ops.append(
                    PatchOp(
                        action=PatchAction.ADD_FIELD,
                        target=f"datasource:{ds_name}/field:{caption}",
                        attribute=None,
                        old_value=None,
                        new_value=caption,
                    )
                )
            for caption in ds_diff.fields_removed:
                ops.append(
                    PatchOp(
                        action=PatchAction.REMOVE_FIELD,
                        target=f"datasource:{ds_name}/field:{caption}",
                        attribute=None,
                        old_value=caption,
                        new_value=None,
                    )
                )
            for caption, field_diffs in ds_diff.fields_modified.items():
                for fd in field_diffs:
                    ops.append(
                        PatchOp(
                            action=PatchAction.MODIFY_FIELD,
                            target=f"datasource:{ds_name}/field:{caption}",
                            attribute=fd.attribute,
                            old_value=fd.old_value,
                            new_value=fd.new_value,
                        )
                    )
            for conn_change in ds_diff.connections_modified:
                ops.append(
                    PatchOp(
                        action=PatchAction.MODIFY_CONNECTION,
                        target=f"datasource:{ds_name}/connection:{conn_change.get('index', 0)}",
                        attribute=conn_change.get("attribute"),
                        old_value=conn_change.get("old"),
                        new_value=conn_change.get("new"),
                    )
                )

        for name in diff.worksheets_added:
            ops.append(
                PatchOp(
                    action=PatchAction.ADD_WORKSHEET,
                    target=f"worksheet:{name}",
                    attribute=None,
                    old_value=None,
                    new_value=name,
                )
            )
        for name in diff.worksheets_removed:
            ops.append(
                PatchOp(
                    action=PatchAction.REMOVE_WORKSHEET,
                    target=f"worksheet:{name}",
                    attribute=None,
                    old_value=name,
                    new_value=None,
                )
            )

        return cls(ops=ops)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# apply_patch
# ---------------------------------------------------------------------------


def _parse_target(target: str) -> dict[str, str]:
    """Parse 'datasource:name/field:caption' → {'datasource': 'name', 'field': 'caption'}."""
    parts: dict[str, str] = {}
    for segment in target.split("/"):
        if ":" in segment:
            k, _, v = segment.partition(":")
            parts[k] = v
    return parts


def apply_patch(workbook: Workbook, patch: Patch, *, validate: bool = True) -> int:
    """Apply a :class:`Patch` to a workbook in place.

    Unknown or missing targets are skipped with a warning. Returns the
    number of ops successfully applied.
    """
    from pytableau.core.state import fingerprint, install, snapshot

    original = snapshot(workbook)
    applied = 0
    try:
        for op in patch.ops:
            if op.action == "replace_snapshot":
                if fingerprint(snapshot(workbook)) != op.old_value:
                    raise ValueError("Patch conflict: workbook XML or assets changed")
                install(workbook, op.new_value)
                applied += 1
            else:
                try:
                    prior = fingerprint(snapshot(workbook))
                    _apply_op(workbook, op)
                    applied += int(fingerprint(snapshot(workbook)) != prior)
                except (KeyError, AttributeError) as exc:
                    warnings.warn(
                        f"Patch op skipped (target not found): {op.target!r} — {exc}", stacklevel=2
                    )
        if validate:
            errors = [i for i in workbook.validate() if i.level == "error"]
            if errors:
                from pytableau.exceptions import SchemaValidationError

                raise SchemaValidationError(f"Workbook is invalid after patch: {errors[0]}")
    except BaseException:
        install(workbook, original, restore_tombstones=True)
        raise
    return applied


def _apply_op(workbook: Workbook, op: PatchOp) -> None:
    parts = _parse_target(op.target)
    action = op.action

    if action == PatchAction.MODIFY_CONNECTION:
        ds_name = parts.get("datasource")
        if ds_name:
            ds = workbook.datasources[ds_name]
            conn_idx = int(parts.get("connection", "0"))
            conn = ds.connections[conn_idx]
            if op.attribute is None:
                raise ValueError("Connection edits require an attribute")
            attribute = op.attribute if op.attribute != "class" else "class_"
            if attribute not in {"class_", "server", "dbname", "username", "port"}:
                raise ValueError(f"Unsupported connection attribute: {attribute}")
            if op.old_value is not None and str(getattr(conn, attribute)) != str(op.old_value):
                raise ValueError(f"Patch conflict: {op.target}.{attribute}")
            setattr(conn, op.attribute if op.attribute != "class" else "class_", op.new_value)
        else:
            raise ValueError("Connection patch requires a datasource")
        return

    if action == PatchAction.MODIFY_FIELD:
        if op.target == "workbook" and op.attribute == "version":
            if op.old_value is not None and str(op.old_value) != workbook.version:
                raise ValueError("Patch conflict: workbook.version")
            if op.new_value:
                workbook.migrate_version(str(op.new_value))
            return
        ds_name = parts.get("datasource")
        field_caption = parts.get("field")
        if ds_name and field_caption:
            ds = workbook.datasources[ds_name]
            f = ds.get_field(field_caption)
            if f is None:
                raise KeyError(f"Field {field_caption!r} not found in datasource {ds_name!r}")
            attr = op.attribute
            if op.old_value is not None and str(getattr(f, attr or "")) != str(op.old_value):
                raise ValueError(f"Patch conflict: {op.target}.{attr}")
            if attr == "formula":
                from pytableau.core.fields import CalculatedField

                if not isinstance(f, CalculatedField):
                    raise ValueError("Formula edits require a calculated field")
                f.formula = str(op.new_value or "")
            elif attr == "hidden":
                f.hidden = str(op.new_value).lower() in {"true", "1", "yes"}
            elif attr in {"datatype", "role", "caption"}:
                setattr(f, attr, op.new_value)
            else:
                raise ValueError(f"Unsupported field attribute: {attr}")
        else:
            raise ValueError("Field patch requires a datasource and field")
        return

    if action in (
        PatchAction.ADD_DATASOURCE,
        PatchAction.REMOVE_DATASOURCE,
        PatchAction.ADD_WORKSHEET,
        PatchAction.REMOVE_WORKSHEET,
        PatchAction.ADD_DASHBOARD,
        PatchAction.REMOVE_DASHBOARD,
        PatchAction.ADD_FIELD,
        PatchAction.REMOVE_FIELD,
    ):
        from lxml import etree

        tags = {"datasource": "datasources", "worksheet": "worksheets", "dashboard": "dashboards"}
        tag = next((t for t in ("field", *tags) if t in parts), None)
        if tag is None:
            raise ValueError(f"Invalid structural target: {op.target}")
        parent: Any
        if tag == "field":
            parent = workbook.datasources[parts["datasource"]].xml_node
            columns = parent.find("columns")
            if columns is not None:
                parent = columns
            xml_tag = "column"
        else:
            parent = workbook.xml_root.find(tags[tag])
            if parent is None:
                parent = etree.SubElement(workbook.xml_root, tags[tag])
            xml_tag = tag
        found = [
            n for n in parent.findall(xml_tag) if parts[tag] in {n.get("name"), n.get("caption")}
        ]
        if str(action).startswith("remove_"):
            if len(found) != 1:
                raise KeyError(op.target)
            if op.old_value is not None:
                from pytableau.core.state import xml_identity

                if not isinstance(op.old_value, str) or xml_identity(op.old_value) != xml_identity(
                    etree.tostring(found[0], with_tail=False)
                ):
                    raise ValueError(f"Patch conflict: {op.target}")
            parent.remove(found[0])
        else:
            if found:
                raise ValueError(f"Target already exists: {op.target}")
            if not isinstance(op.new_value, str) or not op.new_value.lstrip().startswith("<"):
                raise ValueError("Structural additions require complete XML payloads")
            node = etree.fromstring(
                op.new_value.encode(), etree.XMLParser(resolve_entities=False, no_network=True)
            )
            if node.tag != xml_tag:
                raise ValueError(f"Expected <{xml_tag}> payload")
            names = {node.get("name"), node.get("caption")}
            payload_name = node.get("name")
            if tag == "field" and payload_name:
                names.add(payload_name[1:-1])
            if parts[tag] not in names:
                raise ValueError("Structural payload identity differs from patch target")
            if any(n.get("name") == node.get("name") for n in parent.findall(xml_tag)):
                raise ValueError("Structural payload duplicates an existing identity")
            parent.append(node)
        workbook._load_tree(workbook.xml_tree)
        return
    raise ValueError(f"Unknown patch action: {action}")
