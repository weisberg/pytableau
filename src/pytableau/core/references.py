"""Lossless Tableau references, scoped resolution, and mutation impact analysis."""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from lxml import etree

if TYPE_CHECKING:
    from pytableau.core.datasource import Datasource
    from pytableau.core.fields import Field
    from pytableau.core.workbook import Workbook

_BRACKET = r"\[(?:[^\]]|\]\])+\]"
_TOKEN = re.compile(rf"{_BRACKET}(?:\.{_BRACKET})*")
_PARTS = re.compile(_BRACKET)
_ENCODINGS = frozenset(
    [
        "sum",
        "avg",
        "min",
        "max",
        "cnt",
        "cntd",
        "ctd",
        "clct",
        "attr",
        "usr",
        "none",
        "med",
        "stdev",
        "var",
        "yr",
        "qr",
        "mn",
        "wk",
        "dy",
        "hour",
        "pcto",
        "pcdf",
        "pcva",
        "cum",
        "tdy",
        "tmn",
        "tyr",
        "thr",
        "hr",
        "my",
        "wd",
        "pctd",
        "cumu",
        "diff",
        "rank",
        "dense_rank",
        "index",
        "total",
        "running",
        "window",
        "lod",
        "tvar",
        "tstd",
    ]
)
_KINDS = re.compile(r"^(.*):([nqo]k)(:\d+)?$")
_BUILTINS = frozenset(
    {
        "Measure Names",
        "Measure Values",
        ":Measure Names",
        ":Measure Values",
        "Number of Records",
        "Multiple Values",
        "Latitude (generated)",
        "Longitude (generated)",
        "Geometry (generated)",
    }
)


def _unbracket(value: str) -> str:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1].replace("]]", "]")
    return text


def _bracket(value: str) -> str:
    return "[" + value.replace("]", "]]") + "]"


@dataclass(frozen=True)
class FieldReference:
    """A field identity plus its original instance encoding.

    ``name`` is the base field name; ``instance`` retains native encodings such
    as ``pcto:sum:Sales:qk:10``. Simple ``FieldReference("Sales")`` remains valid.
    Instance aliases are resolved against dependency definitions, not guessed.
    """

    name: str
    datasource: str | None = None
    aggregation: str | None = None
    derivation: str | None = None
    instance: str | None = None
    qualifiers: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> FieldReference:
        """Parse one bracketed, qualified, or bare reference losslessly."""
        text = text.strip()
        if not text.startswith("["):
            return cls(text)
        if _TOKEN.fullmatch(text) is None:
            raise ValueError(f"Invalid field reference: {text!r}")
        parts = [_unbracket(p.group()) for p in _PARTS.finditer(text)]
        source, encoded = (parts[0], parts[-1]) if len(parts) > 1 else (None, parts[0])
        qualifiers = tuple(parts[1:-1])
        match = _KINDS.match(encoded)
        if match:
            stem, kind, _ = match.groups()
            segments = stem.split(":")
            codes = []
            while len(segments) > 1 and segments[0].lower() in _ENCODINGS:
                codes.append(segments.pop(0))
            if codes:
                return cls(":".join(segments), source, codes[-1], kind, encoded, qualifiers)
        return cls(encoded, source, qualifiers=qualifiers)

    def __str__(self) -> str:
        encoded = self.instance
        if encoded is None:
            encoded = self.name
            if self.aggregation is not None:
                encoded = f"{self.aggregation.lower()}:{encoded}:{self.derivation or 'qk'}"
        token = _bracket(encoded)
        prefix = ([self.datasource] if self.datasource else []) + list(self.qualifiers)
        return ".".join([*(_bracket(part) for part in prefix), token])

    def with_name(self, name: str) -> FieldReference:
        """Change the base name while retaining aggregation and instance suffix."""
        instance = self.instance
        if instance is not None:
            parsed = _KINDS.match(instance)
            if parsed:
                stem, kind, suffix = parsed.groups()
                prefix = stem[: -len(self.name)] if self.name else stem
                instance = f"{prefix}{name}:{kind}{suffix or ''}"
        return replace(self, name=name, instance=instance)

    @property
    def is_builtin(self) -> bool:
        """Whether the reference denotes a Tableau-generated field/object."""
        return (
            self.name in _BUILTINS
            or self.datasource == "__tableau_internal_object_id__"
            or "__tableau_internal_object_id__" in self.qualifiers
            or self.name.startswith("__tableau_internal_")
        )


@dataclass(frozen=True)
class ReferenceToken:
    reference: FieldReference
    start: int
    end: int


def reference_tokens(text: str, *, formula: bool = False) -> list[ReferenceToken]:
    """Find references, ignoring quoted strings/comments in formula text."""
    out = []
    i = 0
    while i < len(text):
        if formula and text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end + 1
            continue
        if formula and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        if formula and text[i] in {"'", '"'}:
            quote = text[i]
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                elif text[i] == quote:
                    if i + 1 < len(text) and text[i + 1] == quote:
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            continue
        match = _TOKEN.match(text, i)
        if match:
            out.append(ReferenceToken(FieldReference.parse(match.group()), i, match.end()))
            i = match.end()
        else:
            i += 1
    return out


def _location_tokens(node: etree._Element, text: str, kind: str) -> list[ReferenceToken]:
    tokens = reference_tokens(text, formula=kind == "calculation")
    if node.tag != "run":
        return tokens
    previous, following = node.getprevious(), node.getnext()
    return [
        token
        for token in tokens
        if (
            text[max(0, token.start - 1) : token.start] == "<"
            and text[token.end : token.end + 1] == ">"
        )
        or (
            text.strip() == str(token.reference)
            and previous is not None
            and following is not None
            and (previous.text or "").endswith("<")
            and (following.text or "").startswith(">")
        )
    ]


@dataclass(frozen=True)
class ReferenceUse:
    """A resolved (or explicitly unresolved) reference at an XML location."""

    reference: FieldReference
    datasource: str | None
    field_id: str | None
    owner: str
    kind: str
    path: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": str(self.reference),
            "datasource": self.datasource,
            "field_id": self.field_id,
            "owner": self.owner,
            "kind": self.kind,
            "path": self.path,
            "error": self.error,
        }


class ReferenceGraph:
    """Resolve references through datasource and column-instance identities."""

    def __init__(self, workbook: Workbook) -> None:
        self.workbook = workbook
        self._sources = list(workbook.datasources)
        if workbook.parameters is not None:
            self._sources.append(workbook.parameters)
        self.uses: list[ReferenceUse] = []
        self._local_fields: dict[str, list[Field]] = {}
        self._calc_owners: dict[str, tuple[str, str]] = {}
        self._locations: list[
            tuple[etree._Element, str | None, str, list[str], str, str, dict[str, str] | None]
        ] = []
        self._scan()

    def resolve(
        self,
        ref: FieldReference,
        sources: list[str] | None = None,
        *,
        aliases: dict[str, str] | None = None,
    ) -> tuple[Datasource | None, Field | None, str | None]:
        """Return a unique owner/field or a diagnostic; never pick an ambiguous match."""
        if ref.is_builtin:
            return None, None, None
        if aliases and str(ref) in aliases:
            resolved_alias = FieldReference.parse(aliases[str(ref)])
            if resolved_alias.datasource:
                ref = resolved_alias
        candidates = self._sources
        if ref.datasource:
            candidates = [d for d in candidates if ref.datasource in {d.name, d.caption}]
            if not candidates:
                return None, None, f"Unknown datasource {ref.datasource!r}"
        elif sources:
            candidates = [
                d
                for d in candidates
                if d.name in sources or d.caption in sources or d.is_parameters
            ]
        name = ref.name
        if aliases:
            alias = aliases.get(str(ref)) or aliases.get(str(replace(ref, datasource=None)))
            if alias:
                name = FieldReference.parse(alias).name
        matches: list[tuple[Datasource, Field]] = []
        captions: list[tuple[Datasource, Field]] = []
        for ds in candidates:
            from pytableau.core.fields import Field

            groups = [Field(n, ds) for n in ds.xml_node.findall("group")]
            for field in [*ds.all_fields, *groups, *self._local_fields.get(ds.name, [])]:
                if name == _unbracket(field.name):
                    if not any(d.name == ds.name and f.name == field.name for d, f in matches):
                        matches.append((ds, field))
                elif name == field.caption and not any(
                    d.name == ds.name and f.name == field.name for d, f in captions
                ):
                    captions.append((ds, field))
        if not matches:
            matches = captions
        if len(matches) == 1:
            return matches[0][0], matches[0][1], None
        if not matches:
            return None, None, f"Unknown field {str(ref)!r}"
        return None, None, f"Ambiguous field {str(ref)!r}; qualify its datasource"

    def _add(
        self,
        node: etree._Element,
        attr: str | None,
        sources: list[str],
        owner: str,
        kind: str,
        *,
        aliases: dict[str, str] | None = None,
    ) -> None:
        text = node.get(attr, "") if attr else node.text or ""
        tokens = _location_tokens(node, text, kind)
        if node.tag == "run":
            kind = "formatted_text"
        if not tokens:
            return
        self._locations.append((node, attr, text, sources, owner, kind, aliases))
        base = self.workbook.xml_tree.getpath(node)
        parent = node.getparent()
        if kind == "calculation" and parent is not None and sources:
            self._calc_owners[base + "/@formula"] = (sources[0], parent.get("name", ""))
        for token in tokens:
            ds, field, error = self.resolve(token.reference, sources, aliases=aliases)
            self.uses.append(
                ReferenceUse(
                    token.reference,
                    ds.name if ds else None,
                    field.name if field else None,
                    owner,
                    kind,
                    base + (f"/@{attr}" if attr else "/text()"),
                    error,
                )
            )

    def _scan(self) -> None:
        for ds in self._sources:
            for node in ds.xml_node.findall(".//groupfilter[@level]"):
                self._add(node, "level", [ds.name], f"datasource:{ds.name}", "group")
            for node in ds.xml_node.findall(".//drill-path/field"):
                self._add(node, None, [ds.name], f"datasource:{ds.name}", "hierarchy")
            for node in ds.xml_node.findall(".//relationships/relationship//expression"):
                if node.get("op", "").startswith("["):
                    self._add(node, "op", [ds.name], f"datasource:{ds.name}", "relationship")
            for join in ds.xml_node.findall(".//relation[@type='join']"):
                join_aliases = {}
                for leaf in join.findall(".//relation"):
                    name = leaf.get("name")
                    if not name:
                        continue
                    for record in ds.metadata_records:
                        if record.parent_name.strip("[]") == name:
                            join_aliases[str(FieldReference(record.remote_name, name))] = str(
                                FieldReference(_unbracket(record.local_name), ds.name)
                            )
                    for field in ds.all_fields:
                        join_aliases.setdefault(
                            str(FieldReference(_unbracket(field.name), name)),
                            str(FieldReference(_unbracket(field.name), ds.name)),
                        )
                for node in join.findall("clause//expression"):
                    if node.get("op", "").startswith("["):
                        self._add(
                            node,
                            "op",
                            [ds.name],
                            f"datasource:{ds.name}",
                            "join",
                            aliases=join_aliases,
                        )
            for node in ds.xml_node.findall(".//calculation"):
                self._add(node, "formula", [ds.name], f"datasource:{ds.name}", "calculation")
        attrs = {"column", "field", "measure", "x-axis-name", "y-axis-name", "sort-column"}
        for ws in self.workbook.worksheets:
            aliases: dict[str, str] = {}
            self._local_fields = {}
            ambiguous_aliases: set[str] = set()
            for container in ws.xml_node.findall(".//datasource-dependencies"):
                source = container.get("datasource")
                if source:
                    ds = next((d for d in self._sources if d.name == source), None)
                    if ds:
                        self._local_fields[source] = [
                            ds._field_from_node(n)
                            for n in container.findall("column")
                            if n.find("calculation") is not None
                        ]
            for container in ws.xml_node.findall(".//datasource-dependencies"):
                source = container.get("datasource")
                if source is None and len(ws.datasource_dependencies) == 1:
                    source = ws.datasource_dependencies[0]
                for instance in container.findall("column-instance"):
                    name, column = instance.get("name"), instance.get("column")
                    if name and column:
                        if name in aliases and aliases[name] != column:
                            ambiguous_aliases.add(name)
                        elif name not in ambiguous_aliases:
                            aliases[name] = column
                        if source:
                            aliases[f"{_bracket(source)}.{name}"] = column
            for name in ambiguous_aliases:
                aliases.pop(name, None)
            for calculation in ws.xml_node.findall(".//datasource-dependencies/column/calculation"):
                container = calculation.getparent().getparent()
                source = container.get("datasource")
                self._add(
                    calculation,
                    "formula",
                    [source] if source else ws.datasource_dependencies,
                    f"worksheet:{ws.name}",
                    "calculation",
                    aliases=aliases,
                )
            for node in ws.xml_node.iter():
                tag = etree.QName(node).localname if isinstance(node.tag, str) else ""
                if tag in {"column", "calculation"}:
                    continue
                if tag in {
                    "rows",
                    "cols",
                    "color",
                    "size",
                    "detail",
                    "tooltip",
                    "label",
                    "text",
                    "run",
                }:
                    self._add(
                        node,
                        None,
                        ws.datasource_dependencies,
                        f"worksheet:{ws.name}",
                        "worksheet",
                        aliases=aliases,
                    )
                for attr in attrs & set(node.attrib):
                    if (
                        tag == "filter"
                        and node.get("class") == "wildcard"
                        and "Tooltip (" in node.get(attr, "")
                    ):
                        continue
                    self._add(
                        node,
                        attr,
                        ws.datasource_dependencies,
                        f"worksheet:{ws.name}",
                        "worksheet",
                        aliases=aliases,
                    )
                if tag == "alias" and "key" in node.attrib:
                    self._add(
                        node,
                        "key",
                        ws.datasource_dependencies,
                        f"worksheet:{ws.name}",
                        "worksheet",
                        aliases=aliases,
                    )
        self._local_fields = {}
        for dashboard in self.workbook.dashboards:
            for action in dashboard.actions:
                sheet = action.source_sheet or action.target_sheet
                sources = []
                if sheet is not None:
                    with suppress(KeyError):
                        sources = self.workbook.worksheets[sheet].datasource_dependencies
                for node in action.xml_node.iter():
                    for attr in {
                        "field",
                        "column",
                        "source-field",
                        "target-field",
                        "name",
                    } & set(node.attrib):
                        if attr != "name" or node.tag == "field":
                            self._add(node, attr, sources, f"dashboard:{dashboard.name}", "action")
                    if node.tag == "field":
                        self._add(node, None, sources, f"dashboard:{dashboard.name}", "action")

    def impact(
        self, field: str, datasource: str | None = None, *, transitive: bool = True
    ) -> list[ReferenceUse]:
        """Preview direct and downstream usages of a uniquely identified field."""
        ref = FieldReference.parse(field)
        if datasource is not None:
            ref = replace(ref, datasource=datasource)
        ds, resolved, error = self.resolve(ref)
        if datasource is not None:
            candidates = [d for d in self._sources if datasource in {d.name, d.caption}]
            if len(candidates) == 1:
                by_caption = candidates[0].get_field(field)
                if by_caption is not None:
                    ds, resolved, error = candidates[0], by_caption, None
        if error or ds is None or resolved is None:
            raise ValueError(error or "A concrete field is required")
        keys = {(ds.name, resolved.name)}
        result = []
        while True:
            selected = [
                u for u in self.uses if (u.datasource, u.field_id) in keys and u not in result
            ]
            if not selected:
                break
            result.extend(selected)
            if not transitive:
                break
            for use in selected:
                if use.path in self._calc_owners:
                    keys.add(self._calc_owners[use.path])
        return result

    def remove_usages(self, datasource: str, field_id: str) -> None:
        """Remove resolved display/filter/action uses; report dependent calculations."""
        import warnings

        from pytableau.exceptions import InvalidWorkbookError

        removals = []
        texts = []
        attributes = []
        for node, attr, text, sources, _owner, kind, aliases in self._locations:
            matching = []
            tokens = _location_tokens(node, text, kind)
            for token in tokens:
                ds, field, error = self.resolve(token.reference, sources, aliases=aliases)
                if error and token.reference.name == _unbracket(field_id):
                    raise InvalidWorkbookError(f"Cannot safely remove ambiguous reference: {error}")
                if ds and field and (ds.name, field.name) == (datasource, field_id):
                    matching.append(token)
            if not matching:
                continue
            if kind in {"join", "relationship"}:
                raise InvalidWorkbookError(
                    "Remove the dependent relationship or join before removing its key field"
                )
            if kind == "calculation":
                warnings.warn(
                    f"Removing {datasource}.{field_id} leaves a dependent calculation at {self.workbook.xml_tree.getpath(node)}",
                    stacklevel=2,
                )
                continue
            if attr and node.tag in {
                "filter",
                "color",
                "size",
                "text",
                "detail",
                "tooltip",
                "column-instance",
                "field",
                "alias",
            }:
                removals.append(node)
            elif attr:
                attributes.append((node, attr))
            elif node.tag in {"rows", "cols", "color", "size", "detail", "label", "tooltip"}:
                remaining = [str(t.reference) for t in tokens if t not in matching]
                parent = node.getparent()
                separator = " / " if parent is not None and parent.tag == "table" else ", "
                texts.append((node, separator.join(remaining)))
            elif node.tag == "field":
                removals.append(node)
            else:
                for token in reversed(matching):
                    text = text[: token.start] + text[token.end :]
                texts.append((node, text))
        for node in removals:
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
        for node, attr in attributes:
            if attr in node.attrib:
                del node.attrib[attr]
        for node, value in texts:
            node.text = value
        for ws in self.workbook.worksheets:
            for container in ws.xml_node.findall(".//datasource-dependencies"):
                if container.get("datasource") == datasource:
                    for column in container.findall("column"):
                        if column.get("name") == field_id:
                            container.remove(column)
            ws._refresh_references()

    def rename(
        self, datasource: str, field_id: str, old: str, new: str, *, internal: bool = False
    ) -> None:
        """Rewrite resolved uses atomically, preserving native internal identities."""
        updates = []
        native = any(
            ws.xml_node.find(".//column-instance") is not None for ws in self.workbook.worksheets
        )
        for node, attr, text, sources, _, kind, aliases in self._locations:
            if kind == "join":
                continue  # Physical keys identify remote columns, not logical field IDs.
            tokens = _location_tokens(node, text, kind)
            replacements = []
            for token in tokens:
                ds, field, error = self.resolve(token.reference, sources, aliases=aliases)
                if error and token.reference.name == old:
                    raise ValueError(error)
                if ds is None or field is None or ds.name != datasource or field.name != field_id:
                    continue
                if not internal and (
                    token.reference.instance is not None
                    or (native and token.reference.name == _unbracket(field_id))
                ):
                    continue
                if not internal and token.reference.name != old:
                    continue
                replacements.append((token.start, token.end, str(token.reference.with_name(new))))
            for start, end, value in reversed(replacements):
                text = text[:start] + value + text[end:]
            if replacements:
                updates.append((node, attr, text))
        for ws in self.workbook.worksheets:
            for container in ws.xml_node.findall(".//datasource-dependencies"):
                if container.get("datasource") != datasource:
                    continue
                for column in container.findall("column"):
                    if column.get("name") == field_id:
                        column.set("caption", new)
                        if internal:
                            column.set("name", str(FieldReference(new)))
                if internal:
                    for instance in container.findall("column-instance"):
                        if instance.get("column") == field_id:
                            encoded = FieldReference.parse(instance.get("name", ""))
                            instance.set("name", str(encoded.with_name(new)))
                            instance.set("column", str(FieldReference(new)))
        for node, attr, value in updates:
            if attr:
                node.set(attr, value)
            else:
                node.text = value
