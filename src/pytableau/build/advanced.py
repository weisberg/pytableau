"""Typed native relations, logical relationships, panes and table calculations."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, replace
from typing import Any

from lxml import etree

from pytableau.core.references import FieldReference


def _expression(keys: tuple[tuple[str, str], ...], *, qualified: bool) -> etree._Element:
    if not keys:
        raise ValueError("At least one key pair is required")
    expressions = []
    for left, right in keys:
        refs = [FieldReference.parse(left), FieldReference.parse(right)]
        if qualified and any(not r.datasource for r in refs):
            raise ValueError("Join keys must be qualified by relation alias")
        predicate = etree.Element("expression", op="=")
        for ref in refs:
            etree.SubElement(predicate, "expression", op=str(ref))
        expressions.append(predicate)
    if len(expressions) == 1:
        return expressions[0]
    root = etree.Element("expression", op="AND")
    root.extend(expressions)
    return root


class RelationBuilder:
    """Compose tables, custom SQL and binary join trees with explicit aliases."""

    def __init__(self, node: etree._Element) -> None:
        self._node = node

    @classmethod
    def table(cls, table: str, *, alias: str, connection: str | None = None) -> RelationBuilder:
        if not table or not alias:
            raise ValueError("Table and alias must be nonempty")
        attrs = {"type": "table", "name": alias, "table": table}
        if connection:
            attrs["connection"] = connection
        return cls(etree.Element("relation", attrib=attrs))

    @classmethod
    def custom_sql(cls, sql: str, *, alias: str, connection: str | None = None) -> RelationBuilder:
        if not sql.strip() or not alias:
            raise ValueError("SQL and alias must be nonempty")
        attrs = {"type": "text", "name": alias}
        if connection:
            attrs["connection"] = connection
        node = etree.Element("relation", attrib=attrs)
        node.text = sql
        return cls(node)

    def join(
        self, other: RelationBuilder, *, keys: tuple[tuple[str, str], ...], how: str = "inner"
    ) -> RelationBuilder:
        if how not in {"inner", "left", "right", "full"}:
            raise ValueError("Invalid join type")
        left_aliases = {n.get("name") for n in self._node.iter("relation") if n.get("name")}
        right_aliases = {n.get("name") for n in other._node.iter("relation") if n.get("name")}
        if left_aliases & right_aliases:
            raise ValueError("Join relations must have distinct aliases")
        for left, right in keys:
            if (
                FieldReference.parse(left).datasource not in left_aliases
                or FieldReference.parse(right).datasource not in right_aliases
            ):
                raise ValueError("Join key alias does not identify its relation side")
        root = etree.Element("relation", type="join", join=how)
        etree.SubElement(root, "clause", type="join").append(_expression(keys, qualified=True))
        root.extend([self.build(), other.build()])
        return RelationBuilder(root)

    def build(self) -> etree._Element:
        return copy.deepcopy(self._node)

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> RelationBuilder:
        kind = spec.get("type", "table")
        if kind == "table":
            return cls.table(spec["table"], alias=spec["alias"], connection=spec.get("connection"))
        if kind in {"text", "sql"}:
            return cls.custom_sql(
                spec["sql"], alias=spec["alias"], connection=spec.get("connection")
            )
        if kind == "join":
            return cls.from_dict(spec["left"]).join(
                cls.from_dict(spec["right"]),
                keys=tuple(tuple(pair) for pair in spec["keys"]),
                how=spec.get("how", "inner"),
            )
        raise ValueError(f"Unknown relation type {kind!r}")


@dataclass(frozen=True)
class LogicalTable:
    id: str
    caption: str
    relation: RelationBuilder

    def build(self) -> etree._Element:
        if not self.id or not self.caption:
            raise ValueError("Logical table ID and caption must be nonempty")
        node = etree.Element("object", id=self.id, caption=self.caption)
        etree.SubElement(node, "properties", context="").append(self.relation.build())
        return node


@dataclass(frozen=True)
class Relationship:
    left: str
    right: str
    keys: tuple[tuple[str, str], ...]

    def build(self) -> etree._Element:
        if self.left == self.right or not self.left or not self.right:
            raise ValueError("Relationship requires two distinct logical tables")
        node = etree.Element("relationship")
        node.append(_expression(self.keys, qualified=False))
        etree.SubElement(node, "first-end-point", attrib={"object-id": self.left})
        etree.SubElement(node, "second-end-point", attrib={"object-id": self.right})
        return node


@dataclass(frozen=True)
class AxisSpec:
    primary: str
    secondary: str
    shelf: str = "rows"
    synchronized: bool = True

    def __post_init__(self) -> None:
        if self.shelf not in {"rows", "cols"} or self.primary == self.secondary:
            raise ValueError("Dual axes require distinct measures on rows or cols")


@dataclass(frozen=True)
class Pane:
    mark_type: str = "Bar"
    axis: str | None = None
    encodings: dict[str, tuple[str, ...]] = field(default_factory=dict)


_QUICK_CALCS = {
    "percent_total": ("PctTotal", "pcto"),
    "percent_difference": ("PctDiff", "pcdf"),
    "running_total": ("CumTotal", "cum"),
    "difference": ("Difference", "diff"),
    "rank": ("Rank", "rank"),
}


@dataclass(frozen=True)
class TableCalculation:
    field: str
    function: str = "percent_total"
    addressing: tuple[str, ...] = ()
    partitioning: tuple[str, ...] = ()
    compute_using: str = "Rows"

    def __post_init__(self) -> None:
        if self.function not in _QUICK_CALCS:
            raise ValueError(f"Unsupported quick table calculation: {self.function}")
        if self.compute_using not in {"Rows", "Columns", "Table", "Pane", "Field"}:
            raise ValueError("Invalid table calculation compute_using")
        if set(self.addressing) & set(self.partitioning):
            raise ValueError("Addressing and partitioning must be disjoint")
        if self.compute_using == "Field" and not self.addressing:
            raise ValueError("Field addressing requires at least one addressing field")

    def instance(self, datasource: str) -> FieldReference:
        ref = native_reference(self.field, datasource)
        _, prefix = _QUICK_CALCS[self.function]
        encoded = str(replace(ref, datasource=None))[1:-1]
        return FieldReference.parse(f"[{datasource}].[{prefix}:{encoded}]")

    def build(self, datasource: str) -> etree._Element:
        kind, _ = _QUICK_CALCS[self.function]
        attrs = {"type": kind, "ordering-type": "Field" if self.addressing else self.compute_using}
        if self.function in {"difference", "percent_difference"}:
            attrs["diff-options"] = "Relative"
        if self.function == "running_total":
            attrs["aggregation"] = "Sum"
        if self.function == "rank":
            attrs["rank-options"] = "Competition,Descending"
        node = etree.Element("table-calc", attrib=attrs)
        if self.function in {"difference", "percent_difference"}:
            etree.SubElement(etree.SubElement(node, "address"), "value").text = "-1"
        for value in self.addressing:
            etree.SubElement(node, "order", field=str(native_reference(value, datasource)))
        # Partitioning is the remaining dimensions in the view; Tableau does not
        # serialize a separate partitioning list in this native representation.
        return node


_AGGREGATIONS = {
    "SUM": ("sum", "Sum", "qk"),
    "AVG": ("avg", "Avg", "qk"),
    "COUNT": ("cnt", "Count", "qk"),
    "COUNTD": ("ctd", "CountD", "qk"),
    "MIN": ("min", "Min", "qk"),
    "MAX": ("max", "Max", "qk"),
    "MEDIAN": ("med", "Median", "qk"),
    "ATTR": ("attr", "Attribute", "nk"),
    "STDEV": ("stdev", "Stdev", "qk"),
    "VAR": ("var", "Var", "qk"),
    "YEAR": ("yr", "Year", "ok"),
    "QUARTER": ("qr", "Quarter", "ok"),
    "MONTH": ("mn", "Month", "ok"),
    "WEEK": ("wk", "Week", "ok"),
    "DAY": ("dy", "Day", "ok"),
}
_DERIVATIONS = {code: derivation for code, derivation, _ in _AGGREGATIONS.values()}
_DERIVATIONS.update({"none": "None", "usr": "User"})


def native_reference(value: str, datasource: str) -> FieldReference:
    match = re.fullmatch(r"([A-Za-z]+)\((.+)\)", value.strip())
    if match:
        aggregation, name = match.groups()
        ref = FieldReference.parse(name)
        if aggregation.upper() not in _AGGREGATIONS:
            raise ValueError(f"Unsupported native aggregation: {aggregation}")
        code, _, kind = _AGGREGATIONS[aggregation.upper()]
        ref = replace(ref, aggregation=code, derivation=kind, instance=None)
    else:
        ref = FieldReference.parse(value)
    if ref.aggregation is None and ref.instance is None:
        ref = replace(ref, aggregation="none", derivation="nk")
    return replace(ref, datasource=ref.datasource or datasource)


def native_worksheet(
    node: etree._Element,
    datasource: str,
    *,
    axes: AxisSpec | None = None,
    panes: tuple[Pane, ...] = (),
    calculations: tuple[TableCalculation, ...] = (),
    definitions: dict[str, dict[str, str]] | None = None,
) -> etree._Element:
    """Transform the basic builder structure to Tableau's native table/view structure."""
    if not datasource:
        raise ValueError("Native authoring requires a datasource binding")
    definitions = definitions or {}
    table = etree.SubElement(node, "table")
    view = etree.SubElement(table, "view")
    etree.SubElement(etree.SubElement(view, "datasources"), "datasource", name=datasource)
    dependencies = etree.SubElement(view, "datasource-dependencies", datasource=datasource)
    defined: set[str] = set()
    instances: set[str] = set()

    def resolved_reference(value: str) -> FieldReference:
        ref = native_reference(value, datasource)
        definition = definitions.get(ref.name, {})
        if definition.get("internal_name"):
            ref = ref.with_name(FieldReference.parse(definition["internal_name"]).name)
        return ref

    def register(value: str, calculation: TableCalculation | None = None) -> str:
        original_reference = native_reference(value, datasource)
        reference = resolved_reference(value)
        calculation = calculation or replacements.get(str(reference))
        if calculation:
            calculation = replace(
                calculation,
                field=str(reference),
                addressing=tuple(str(resolved_reference(v)) for v in calculation.addressing),
                partitioning=tuple(str(resolved_reference(v)) for v in calculation.partitioning),
            )
        if reference.datasource != datasource:
            raise ValueError("Native builder currently requires one datasource per worksheet")
        name = str(FieldReference(reference.name))
        if name not in defined:
            attrs = {
                "name": name,
                "datatype": "real" if reference.aggregation not in {None, "none"} else "string",
                "role": "measure" if reference.aggregation not in {None, "none"} else "dimension",
                "type": "quantitative"
                if reference.aggregation not in {None, "none"}
                else "nominal",
            }
            definition = definitions.get(
                original_reference.name, definitions.get(reference.name, {})
            )
            attrs.update(
                {k: v for k, v in definition.items() if k not in {"internal_name", "formula"}}
            )
            column = etree.SubElement(dependencies, "column", attrib=attrs)
            if "formula" in definition:
                etree.SubElement(
                    column,
                    "calculation",
                    attrib={"class": "tableau", "formula": definition["formula"]},
                )
            defined.add(name)
        result = calculation.instance(datasource) if calculation else reference
        local = str(replace(result, datasource=None))
        if local not in instances:
            instance = etree.SubElement(
                dependencies,
                "column-instance",
                name=local,
                column=name,
                derivation=_DERIVATIONS.get(reference.aggregation or "none", "None"),
                type={"nk": "nominal", "qk": "quantitative", "ok": "ordinal"}.get(
                    reference.derivation or "nk", "nominal"
                ),
                pivot="key",
            )
            if calculation:
                instance.append(calculation.build(datasource))
            instances.add(local)
        return str(result)

    replacements = {str(resolved_reference(c.field)): c for c in calculations}
    shelf_bindings = {}
    for shelf in ("rows", "cols"):
        old = node.find(shelf)
        if old is None:
            old = etree.Element(shelf)
        from pytableau.core.references import reference_tokens

        # Shelf builder entries may contain aggregate expressions inside brackets.
        values = [
            str(t.reference) if t.reference.datasource or t.reference.instance else t.reference.name
            for t in reference_tokens(old.text or "")
        ]
        encoded = [
            register(v, replacements.get(str(native_reference(v, datasource)))) for v in values
        ]
        if axes and axes.shelf == shelf:
            encoded = [register(axes.primary), register(axes.secondary)]
        old.text = " / ".join(encoded)
        shelf_bindings[shelf] = encoded
        table.append(old)
    old_deps = node.find("datasource-dependencies")
    if old_deps is not None:
        node.remove(old_deps)
    filters = node.find("filters")
    if filters is not None:
        for filt in list(filters):
            filt.set("column", register(str(filt.attrib.pop("field"))))
            view.append(filt)
        node.remove(filters)
    style = node.find("style")
    default_mark = style.get("mark", "Automatic") if style is not None else "Automatic"
    if style is not None:
        node.remove(style)
    old_marks = node.find("marks")
    default_encodings = {}
    if old_marks is not None:
        from pytableau.core.references import reference_tokens

        default_encodings = {
            str(n.tag): tuple(str(t.reference) for t in reference_tokens(n.text or ""))
            for n in old_marks
        }
        node.remove(old_marks)
    if not panes:
        panes = (
            tuple(Pane(default_mark.capitalize(), axis) for axis in (axes.primary, axes.secondary))
            if axes
            else (Pane(default_mark.capitalize()),)
        )
    panes_node = etree.SubElement(table, "panes")
    for index, pane in enumerate(panes, 1):
        attrs = {"id": str(index)}
        if pane.axis:
            reference = register(pane.axis)
            bound = [shelf for shelf, values in shelf_bindings.items() if reference in values]
            if len(bound) != 1:
                raise ValueError(f"Pane axis must identify exactly one shelf binding: {pane.axis}")
            attrs["y-axis-name" if bound[0] == "rows" else "x-axis-name"] = reference
        pane_node = etree.SubElement(panes_node, "pane", attrib=attrs)
        etree.SubElement(etree.SubElement(pane_node, "view"), "breakdown", value="auto")
        etree.SubElement(pane_node, "mark", attrib={"class": pane.mark_type})
        encodings = etree.SubElement(pane_node, "encodings")
        for channel, channel_values in {**default_encodings, **pane.encodings}.items():
            if channel not in {
                "color",
                "size",
                "detail",
                "tooltip",
                "label",
                "shape",
                "path",
                "angle",
            }:
                raise ValueError(f"Unsupported mark channel {channel}")
            for value in channel_values:
                etree.SubElement(
                    encodings, "text" if channel == "label" else channel, column=register(value)
                )
        # Addressing and partitioning fields must exist in the view's level of detail.
        for calc in calculations:
            for value in (*calc.addressing, *calc.partitioning):
                reference = register(value)
                if not any(n.get("column") == reference for n in encodings):
                    etree.SubElement(encodings, "detail", column=reference)
    for calc in calculations:
        if (
            str(
                replace(
                    replace(calc, field=str(resolved_reference(calc.field))).instance(datasource),
                    datasource=None,
                )
            )
            not in instances
        ):
            raise ValueError(f"Table calculation field is not used in the view: {calc.field}")
    if axes:
        axis_rule = etree.SubElement(etree.SubElement(table, "style"), "style-rule", element="axis")
        for index, value in enumerate((axes.primary, axes.secondary)):
            etree.SubElement(
                axis_rule,
                "encoding",
                attrib={
                    "attr": "space",
                    "class": str(index),
                    "field": register(value),
                    "field-type": "quantitative",
                    "fold": "true",
                    "scope": axes.shelf,
                    "synchronized": str(axes.synchronized).lower(),
                    "type": "space",
                },
            )
    order = {"view": 0, "style": 1, "panes": 2, "rows": 3, "cols": 4}
    table[:] = sorted(table, key=lambda n: order.get(str(n.tag), 5))
    return node
