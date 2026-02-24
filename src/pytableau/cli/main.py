"""CLI entry point for pytableau — powered by tooli.

Exposes the full pytableau API as a rich, agent-ready command suite with
automatic JSON output, MCP tools, JSON Schema, structured errors with
recovery guidance, and dry-run planning.

Install the CLI extra to use:
    pip install "pytableau[cli]"
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from tooli import Argument, Option, Tooli, dry_run_support, record_dry_action
from tooli.annotations import Destructive, Idempotent, ReadOnly
from tooli.errors import (
    AuthError,
    InputError,
    InternalError,
    StateError,
    ToolError,
    ToolRuntimeError,
)

from pytableau.exceptions import (
    AmbiguousWorkbookError,
    AuthenticationError,
    CorruptWorkbookError,
    DatasourceNotFoundError,
    DuplicateFieldError,
    FieldNotFoundError,
    HyperError,
    InvalidWorkbookError,
    PyTableauError,
    SchemaValidationError,
    ServerError,
    UnmappedPlaceholderError,
)

app = Tooli(
    name="pytableau",
    description="The unified Python SDK for Tableau workbook engineering.",
    version="1.0.0",
)


def _map_error(exc: PyTableauError) -> ToolError:
    """Map a pytableau exception to the appropriate tooli structured error."""
    if isinstance(
        exc,
        (
            InvalidWorkbookError,
            CorruptWorkbookError,
            FieldNotFoundError,
            DuplicateFieldError,
            UnmappedPlaceholderError,
            AmbiguousWorkbookError,
        ),
    ):
        return InputError(str(exc))
    if isinstance(exc, AuthenticationError):
        return AuthError(str(exc))
    if isinstance(exc, (DatasourceNotFoundError, SchemaValidationError)):
        return StateError(str(exc))
    if isinstance(exc, (ServerError, HyperError)):
        return ToolRuntimeError(str(exc))
    return InternalError(str(exc))


# ---------------------------------------------------------------------------
# Inspection group (ReadOnly | Idempotent)
# ---------------------------------------------------------------------------


@app.command(annotations=ReadOnly | Idempotent)
def inspect(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
) -> dict:
    """Inspect a Tableau workbook and return structured metadata."""
    from pytableau.core.workbook import Workbook

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "path": str(workbook),
        "version": wb.version,
        "source_platform": wb.source_platform,
        "datasource_count": len(wb.datasources),
        "datasources": wb.datasources.names,
        "worksheet_count": len(wb.worksheets),
        "worksheets": wb.worksheets.names,
        "dashboard_count": len(wb.dashboards),
        "dashboards": wb.dashboards.names,
    }


@app.command(annotations=ReadOnly | Idempotent)
def validate(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
) -> dict:
    """Validate workbook XML. Returns list of issues."""
    from pytableau.core.workbook import Workbook

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    issues = wb.validate()
    return {
        "path": str(workbook),
        "issue_count": len(issues),
        "issues": [
            {"level": i.level, "message": i.message, "path": i.path} for i in issues
        ],
    }


@app.command(annotations=ReadOnly)
def diff(
    before: Annotated[Path, Argument(help="Path to base .twb or .twbx")],
    after: Annotated[Path, Argument(help="Path to changed .twb or .twbx")],
    semantic: Annotated[bool, Option("--semantic", help="Use semantic object-model diff")] = False,
) -> dict:
    """Show differences between two Tableau workbooks."""
    from pytableau.core.workbook import Workbook

    try:
        before_wb = Workbook.open(before)
        after_wb = Workbook.open(after)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    if semantic:
        wb_diff = before_wb.diff(after_wb)
        return {
            "before": str(before),
            "after": str(after),
            "is_empty": wb_diff.is_empty(),
            "summary": wb_diff.to_text(),
            **wb_diff.to_dict(),
        }

    # XML structural diff
    try:
        from pytableau.xml.differ import xml_diff
        diff_lines = xml_diff(before, after)
    except Exception:
        # Fallback to simple set diff if paths don't resolve to plain .twb
        before_lines = set(before_wb.to_xml_string().splitlines())
        after_lines = set(after_wb.to_xml_string().splitlines())
        added = sorted(after_lines - before_lines)
        removed = sorted(before_lines - after_lines)
        return {
            "before": str(before),
            "after": str(after),
            "added_count": len(added),
            "removed_count": len(removed),
            "added": added,
            "removed": removed,
        }

    added = [ln.rstrip("\n") for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++")]
    removed = [ln.rstrip("\n") for ln in diff_lines if ln.startswith("-") and not ln.startswith("---")]
    return {
        "before": str(before),
        "after": str(after),
        "diff_lines": [ln.rstrip("\n") for ln in diff_lines],
        "added_count": len(added),
        "removed_count": len(removed),
    }


@app.command(annotations=ReadOnly | Idempotent, paginated=True)
def catalog(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    connections: Annotated[bool, Option("--connections", help="Include connection audit")] = False,
) -> list[dict]:
    """List all datasources, fields, calculated fields, and connections."""
    from pytableau.core.workbook import Workbook
    from pytableau.inspect.catalog import WorkbookCatalog

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    cat = WorkbookCatalog(wb)
    if connections:
        return cat.connection_audit()
    data = cat.to_dict()
    return data["datasources"]


@app.command(annotations=ReadOnly | Idempotent)
def lineage(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
) -> dict:
    """Show calculated-field dependency graph."""
    from pytableau.core.workbook import Workbook
    from pytableau.inspect.lineage import FieldLineage

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    graph = FieldLineage(wb)
    return graph.to_dict()


@app.command(annotations=ReadOnly | Idempotent)
def report(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    output: Annotated[
        Path | None, Option(help="Write markdown to this file path")
    ] = None,
) -> dict:
    """Generate markdown documentation for the workbook."""
    from pytableau.core.workbook import Workbook
    from pytableau.inspect.report import WorkbookReport

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    rpt = WorkbookReport(wb)
    markdown = rpt.to_markdown()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")

    return {
        "path": str(workbook),
        "markdown": markdown,
        "output_path": str(output) if output else None,
    }


# ---------------------------------------------------------------------------
# Mutation group (Destructive, with dry-run where safe)
# ---------------------------------------------------------------------------


@app.command(annotations=Destructive | Idempotent, supports_dry_run=True)
@dry_run_support
def swap_connection(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    server: Annotated[str, Option(help="New database server hostname")],
    db: Annotated[str | None, Option(help="New database name")] = None,
    username: Annotated[str | None, Option(help="New database username")] = None,
    output: Annotated[
        Path | None, Option("-o", help="Output path (default: overwrite input)")
    ] = None,
) -> dict:
    """Swap connection properties in a Tableau workbook."""
    from pytableau.core.workbook import Workbook

    destination = output or workbook
    record_dry_action("swap_connection", str(workbook), details={"server": server, "db": db, "output": str(destination)})

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    updated = 0
    for conn in wb.xml_tree.findall(".//connection"):
        conn.set("server", server)
        updated += 1
        if db is not None:
            if "dbname" in conn.attrib:
                conn.set("dbname", db)
            elif "dbName" in conn.attrib:
                conn.set("dbName", db)
            else:
                conn.set("dbname", db)
        if username is not None:
            conn.set("username", username)

    try:
        wb.save_as(destination)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "workbook": str(workbook),
        "output": str(destination),
        "connections_updated": updated,
        "server": server,
        "db": db,
        "username": username,
    }


@app.command(annotations=Destructive, supports_dry_run=True)
@dry_run_support
def rename_field(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    old_name: Annotated[str, Option(help="Current field name")],
    new_name: Annotated[str, Option(help="New field name")],
    output: Annotated[
        Path | None, Option("-o", help="Output path (default: overwrite input)")
    ] = None,
) -> dict:
    """Rename a field and cascade across all worksheets/dashboards."""
    from pytableau.core.workbook import Workbook

    destination = output or workbook
    record_dry_action(
        "rename_field",
        str(workbook),
        details={"old_name": old_name, "new_name": new_name, "output": str(destination)},
    )

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    # Use Datasource.rename_field() which handles caption vs internal name
    # and cascades formula + worksheet reference updates correctly.
    renamed_count = 0
    try:
        for ds in wb.datasources:
            if ds.get_field(old_name) is not None:
                ds.rename_field(old_name, new_name)
                renamed_count += 1
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    try:
        wb.save_as(destination)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "workbook": str(workbook),
        "output": str(destination),
        "old_name": old_name,
        "new_name": new_name,
        "datasources_updated": renamed_count,
    }


@app.command(annotations=Destructive, supports_dry_run=True)
@dry_run_support
def version_migrate(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    target_version: Annotated[str, Option(help="Target Tableau version, e.g. 2024.1")],
    output: Annotated[
        Path | None, Option("-o", help="Output path (default: overwrite input)")
    ] = None,
) -> dict:
    """Migrate a workbook to a different Tableau version."""
    from pytableau.core.workbook import Workbook

    destination = output or workbook
    record_dry_action(
        "version_migrate",
        str(workbook),
        details={"target_version": target_version, "output": str(destination)},
    )

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    original_version = wb.version
    try:
        wb.migrate_version(target_version)
        wb.save_as(destination)
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "workbook": str(workbook),
        "output": str(destination),
        "original_version": original_version,
        "target_version": target_version,
    }


@app.command(annotations=Destructive)
def merge(
    base: Annotated[Path, Argument(help="Path to base .twb or .twbx")],
    other: Annotated[Path, Argument(help="Path to workbook to merge in")],
    output: Annotated[Path, Option("-o", help="Output path for merged workbook")],
) -> dict:
    """Merge sheets/dashboards from another workbook into base."""
    from pytableau.core.workbook import Workbook

    try:
        base_wb = Workbook.open(base)
        other_wb = Workbook.open(other)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    before_sheets = list(base_wb.worksheets.names)
    before_dashboards = list(base_wb.dashboards.names)

    try:
        base_wb.merge(other_wb)
        base_wb.save_as(output)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "base": str(base),
        "other": str(other),
        "output": str(output),
        "worksheets_before": before_sheets,
        "worksheets_after": list(base_wb.worksheets.names),
        "dashboards_before": before_dashboards,
        "dashboards_after": list(base_wb.dashboards.names),
    }


# ---------------------------------------------------------------------------
# Template group
# ---------------------------------------------------------------------------


@app.command(annotations=ReadOnly | Idempotent)
def template_list() -> list[dict]:
    """List all built-in pytableau workbook templates."""
    from pytableau.templates.library import BUILTIN_TEMPLATES

    return [{"name": name} for name in sorted(BUILTIN_TEMPLATES)]


@app.command(annotations=Idempotent)
def template_apply(
    template: Annotated[str, Argument(help="Template name or path to .twb file")],
    output: Annotated[Path, Option("-o", help="Output path for the generated workbook")],
    fields: Annotated[
        list[str] | None, Option(help="KEY=VALUE field mappings")
    ] = None,
) -> dict:
    """Apply a template with field mappings and write output workbook."""
    from pytableau.core.workbook import Workbook
    from pytableau.exceptions import TemplateError

    field_map: dict[str, str] = {}
    if fields:
        for item in fields:
            if "=" not in item:
                raise InputError(f"Field mapping must be KEY=VALUE, got: {item!r}")
            k, _, v = item.partition("=")
            field_map[k.strip()] = v.strip()

    try:
        wb = Workbook.from_template(template, **field_map)
        wb.save_as(output)
    except TemplateError as exc:
        raise InputError(str(exc)) from exc
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "template": template,
        "output": str(output),
        "fields_applied": field_map,
    }


# ---------------------------------------------------------------------------
# Server group
# ---------------------------------------------------------------------------


@app.command(annotations=Destructive, requires_approval=True)
def publish(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx to publish")],
    server: Annotated[str, Option(help="Tableau Server or Cloud URL")],
    project: Annotated[str, Option(help="Target project name or ID")],
    token_name: Annotated[str | None, Option(help="Personal access token name")] = None,
    token_secret: Annotated[
        str | None, Option(help="Personal access token secret")
    ] = None,
) -> dict:
    """Publish a workbook to Tableau Server or Tableau Cloud."""
    from pytableau.core.workbook import Workbook

    auth: dict[str, str] = {}
    if token_name is not None:
        auth["token_name"] = token_name
    if token_secret is not None:
        auth["token_secret"] = token_secret

    try:
        wb = Workbook.open(workbook)
        wb.publish(server, project, **auth)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "workbook": str(workbook),
        "server": server,
        "project": project,
        "status": "published",
    }


@app.command(annotations=ReadOnly | Idempotent)
def complexity(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
) -> dict:
    """Analyze workbook complexity and return a grade + breakdown."""
    from pytableau.core.workbook import Workbook

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    report = wb.complexity_report()
    return {
        "path": str(workbook),
        **report.to_dict(),
    }


@app.command(annotations=Destructive, supports_dry_run=True)
@dry_run_support
def auto_fix(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    output: Annotated[
        Path | None, Option("-o", help="Output path (default: overwrite input)")
    ] = None,
) -> dict:
    """Apply auto-fixers to a workbook (bracket formatting, credential scrubbing, etc.)."""
    from pytableau.core.workbook import Workbook

    destination = output or workbook
    record_dry_action("auto_fix", str(workbook), details={"output": str(destination)})

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    actions = wb.auto_fix(dry_run=False)

    try:
        wb.save_as(destination, scrub_credentials=False)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "workbook": str(workbook),
        "output": str(destination),
        "fixes_applied": len(actions),
        "actions": [
            {"fixer": a.fixer_name, "path": a.path, "old": a.old_value, "new": a.new_value}
            for a in actions
        ],
    }


@app.command(annotations=Destructive, supports_dry_run=True)
@dry_run_support
def promote(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    from_env: Annotated[str, Option("--from-env", help="Source environment name")],
    to_env: Annotated[str, Option("--to-env", help="Target environment name")],
    config_file: Annotated[Path, Option("--config-file", help="Path to promotion config YAML/JSON")],
    output: Annotated[
        Path | None, Option("-o", help="Output path (default: overwrite input)")
    ] = None,
) -> dict:
    """Promote a workbook from one environment to another."""
    from pytableau.core.workbook import Workbook
    from pytableau.package.promotion import PromotionConfig

    destination = output or workbook
    record_dry_action(
        "promote",
        str(workbook),
        details={"from_env": from_env, "to_env": to_env, "output": str(destination)},
    )

    suffix = config_file.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            cfg = PromotionConfig.from_yaml(str(config_file))
        else:
            import json
            cfg = PromotionConfig.from_dict(json.loads(config_file.read_text()))
    except Exception as exc:
        raise InputError(f"Failed to load promotion config: {exc}") from exc

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    try:
        changes = wb.promote(from_env, to_env, cfg)
        wb.save_as(destination, scrub_credentials=False)
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "workbook": str(workbook),
        "output": str(destination),
        "from_env": from_env,
        "to_env": to_env,
        "changes": len(changes),
        "details": [c._asdict() for c in changes],
    }


@app.command(annotations=ReadOnly | Idempotent)
def to_json(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    output: Annotated[
        Path | None, Option("-o", help="Write JSON to this path (default: stdout)")
    ] = None,
) -> dict:
    """Serialize a workbook to canonical JSON for version control."""
    from pytableau.core.workbook import Workbook

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    json_str = wb.to_json()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json_str, encoding="utf-8")

    import json as _json
    return {
        "path": str(workbook),
        "output": str(output) if output else None,
        "canonical": _json.loads(json_str),
    }


@app.command(annotations=Destructive, supports_dry_run=True)
@dry_run_support
def git_clean(
    workbook: Annotated[Path, Argument(help="Path to .twb file to clean")],
) -> dict:
    """Strip thumbnails and volatile attributes for VCS-friendly diffs."""
    from pytableau.xml.canonical import git_clean as _gc

    record_dry_action("git_clean", str(workbook))

    try:
        _gc(workbook, in_place=True)
    except Exception as exc:
        raise InputError(f"Failed to clean workbook: {exc}") from exc

    return {
        "workbook": str(workbook),
        "status": "cleaned",
    }


@app.command(annotations=Destructive, supports_dry_run=True)
@dry_run_support
def patch(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx to patch")],
    patch_file: Annotated[Path, Option("--patch-file", help="Path to JSON patch file")],
    output: Annotated[
        Path | None, Option("-o", help="Output path (default: overwrite input)")
    ] = None,
) -> dict:
    """Apply a JSON patch file to a workbook."""
    import json as _json

    from pytableau.core.workbook import Workbook
    from pytableau.inspect.diff import Patch

    destination = output or workbook
    record_dry_action("patch", str(workbook), details={"patch_file": str(patch_file), "output": str(destination)})

    try:
        patch_obj = Patch.from_dict(_json.loads(patch_file.read_text()))
    except Exception as exc:
        raise InputError(f"Invalid patch file: {exc}") from exc

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    applied = wb.apply(patch_obj, validate=True)

    try:
        wb.save_as(destination, scrub_credentials=False)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "workbook": str(workbook),
        "output": str(destination),
        "ops_total": len(patch_obj.ops),
        "ops_applied": applied,
    }


@app.command(annotations=ReadOnly | Idempotent)
def formula_lint(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
) -> dict:
    """Lint all calculated field formulas in a workbook."""
    from pytableau.calculations.linter import lint_workbook
    from pytableau.core.workbook import Workbook

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    issues = lint_workbook(wb)
    return {
        "path": str(workbook),
        "issue_count": len(issues),
        "issues": [i.to_dict() for i in issues],
    }


@app.command(annotations=ReadOnly | Idempotent)
def formula_parse(
    formula: Annotated[str, Argument(help="Tableau formula string to parse")],
) -> dict:
    """Parse a Tableau formula string and return the AST as JSON."""
    import dataclasses

    try:
        from pytableau.calculations.parser import parse
    except ImportError as exc:
        raise InputError(f"Formula parsing requires pytableau[analysis]: {exc}") from exc

    try:
        ast = parse(formula)
    except Exception as exc:
        return {
            "formula": formula,
            "success": False,
            "error": str(exc),
            "ast": None,
        }

    def _node_to_dict(node):
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            d = {"_type": type(node).__name__}
            for f in dataclasses.fields(node):
                val = getattr(node, f.name)
                if isinstance(val, list):
                    val = [_node_to_dict(v) if dataclasses.is_dataclass(v) else v for v in val]
                elif dataclasses.is_dataclass(val):
                    val = _node_to_dict(val)
                d[f.name] = val
            return d
        return node

    return {
        "formula": formula,
        "success": True,
        "ast": _node_to_dict(ast),
    }


@app.command(annotations=ReadOnly | Idempotent)
def server_list(
    server: Annotated[str, Option(help="Tableau Server or Cloud URL")],
    project: Annotated[str | None, Option(help="Filter by project ID")] = None,
    token_name: Annotated[str | None, Option(help="Personal access token name")] = None,
    token_secret: Annotated[
        str | None, Option(help="Personal access token secret")
    ] = None,
) -> dict:
    """List workbooks on a Tableau Server or Cloud instance."""
    from pytableau.server.client import ServerClient

    auth: dict[str, str] = {}
    if token_name is not None:
        auth["token_name"] = token_name
    if token_secret is not None:
        auth["token_secret"] = token_secret

    try:
        with ServerClient(server, **auth) as client:
            workbooks = client.list_workbooks(project_id=project, **auth)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "server": server,
        "workbook_count": len(workbooks),
        "workbooks": workbooks,
    }


@app.command(annotations=ReadOnly)
def download(
    workbook_id: Annotated[str, Argument(help="Workbook ID on Tableau Server or Cloud")],
    server: Annotated[str, Option(help="Tableau Server or Cloud URL")],
    output: Annotated[Path, Option("-o", help="Local path to save downloaded workbook")],
    token_name: Annotated[str | None, Option(help="Personal access token name")] = None,
    token_secret: Annotated[
        str | None, Option(help="Personal access token secret")
    ] = None,
) -> dict:
    """Download a workbook from Tableau Server or Cloud."""
    from pytableau.core.workbook import Workbook

    auth: dict[str, str] = {}
    if token_name is not None:
        auth["token_name"] = token_name
    if token_secret is not None:
        auth["token_secret"] = token_secret

    try:
        _wb = Workbook.new()
        downloaded = _wb.download(server, workbook_id, **auth)
        downloaded.save_as(output)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    return {
        "workbook_id": workbook_id,
        "server": server,
        "output": str(output),
        "status": "downloaded",
    }


# ---------------------------------------------------------------------------
# Governance group
# ---------------------------------------------------------------------------


@app.command(annotations=ReadOnly | Idempotent)
def governance_lint(
    workbook: Annotated[Path, Argument(help="Path to .twb or .twbx")],
    ruleset: Annotated[
        Path | None, Option("--ruleset", "-r", help="Path to YAML ruleset file")
    ] = None,
    exit_code: Annotated[
        bool, Option("--exit-code", help="Exit with code 1 if any errors found")
    ] = False,
) -> dict:
    """Lint a workbook against governance rules."""
    import sys

    from pytableau.core.workbook import Workbook
    from pytableau.governance.rules import GovernanceRuleset, lint_with_ruleset

    try:
        wb = Workbook.open(workbook)
    except PyTableauError as exc:
        raise _map_error(exc) from exc

    rs = GovernanceRuleset.from_yaml(ruleset) if ruleset is not None else GovernanceRuleset.default()
    issues = lint_with_ruleset(wb, rs)

    result = {
        "path": str(workbook),
        "passed": not any(i.severity == "error" for i in issues),
        "issue_count": len(issues),
        "issues": [
            {"rule": i.rule, "severity": i.severity, "message": i.message}
            for i in issues
        ],
    }

    if exit_code and not result["passed"]:
        sys.exit(1)

    return result


@app.command(annotations=Destructive, supports_dry_run=True)
@dry_run_support
def index_workbooks(
    directory: Annotated[Path, Argument(help="Directory to scan for workbooks")],
    db: Annotated[Path, Option("--db", help="SQLite database path")] = Path("pytableau.db"),
) -> dict:
    """Index all workbooks in a directory into a SQLite database."""
    from pytableau.governance.index import WorkbookIndex

    record_dry_action("index_workbooks", str(directory), details={"db": str(db)})

    with WorkbookIndex(db) as idx:
        count = idx.add_directory(directory)

    return {
        "directory": str(directory),
        "db": str(db),
        "workbooks_indexed": count,
    }


@app.command(annotations=ReadOnly | Idempotent)
def search_index(
    term: Annotated[str, Argument(help="Search term")],
    db: Annotated[Path, Option("--db", help="SQLite database path")] = Path("pytableau.db"),
    kind: Annotated[
        str, Option("--kind", help="Search kind: 'field' or 'connection'")
    ] = "field",
) -> list:
    """Search a workbook index for fields or connections."""
    from pytableau.governance.index import WorkbookIndex

    with WorkbookIndex(db) as idx:
        if kind == "connection":
            return idx.search_connection(term)
        return idx.search_field(term)
