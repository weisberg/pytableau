"""SQLite-backed cross-workbook field and connection index."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

_DDL = """
CREATE TABLE IF NOT EXISTS workbooks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT UNIQUE NOT NULL,
    version     TEXT,
    indexed_at  TEXT
);
CREATE TABLE IF NOT EXISTS fields (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workbook_id  INTEGER,
    datasource   TEXT,
    caption      TEXT,
    formula      TEXT,
    is_calculated INTEGER,
    FOREIGN KEY(workbook_id) REFERENCES workbooks(id)
);
CREATE TABLE IF NOT EXISTS connections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workbook_id  INTEGER,
    datasource   TEXT,
    class_       TEXT,
    server       TEXT,
    dbname       TEXT,
    FOREIGN KEY(workbook_id) REFERENCES workbooks(id)
);
"""


class WorkbookIndex:
    """SQLite-backed index for searching across multiple Tableau workbooks.

    Example::

        with WorkbookIndex(":memory:") as idx:
            idx.add("sales.twb")
            results = idx.search_field("Region")
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> WorkbookIndex:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, path: str | Path) -> None:
        """Index a single workbook file.

        Args:
            path: Path to a ``.twb`` or ``.twbx`` file.
        """
        from pytableau.core.workbook import Workbook

        path = Path(path).resolve()
        wb = Workbook.open(path)
        now = datetime.now(timezone.utc).isoformat()

        cur = self._conn.cursor()

        # Upsert workbook row
        cur.execute(
            "INSERT INTO workbooks(path, version, indexed_at) VALUES (?, ?, ?)"
            " ON CONFLICT(path) DO UPDATE SET version=excluded.version, indexed_at=excluded.indexed_at",
            (str(path), wb.version, now),
        )
        wb_id: int = cur.execute(
            "SELECT id FROM workbooks WHERE path = ?", (str(path),)
        ).fetchone()[0]

        # Remove stale rows
        cur.execute("DELETE FROM fields WHERE workbook_id = ?", (wb_id,))
        cur.execute("DELETE FROM connections WHERE workbook_id = ?", (wb_id,))

        # Insert fields
        for ds in wb.datasources:
            for f in ds.fields:
                formula = getattr(f, "formula", None)
                is_calc = 1 if formula else 0
                cur.execute(
                    "INSERT INTO fields(workbook_id, datasource, caption, formula, is_calculated)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (wb_id, ds.name, f.caption, formula, is_calc),
                )
            # Insert connections
            for conn in ds.connections:
                class_ = conn.xml_node.get("class", "")
                server = conn.xml_node.get("server", "")
                dbname = conn.xml_node.get("dbname") or conn.xml_node.get("dbName", "")
                cur.execute(
                    "INSERT INTO connections(workbook_id, datasource, class_, server, dbname)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (wb_id, ds.name, class_, server, dbname),
                )

        self._conn.commit()

    def add_directory(
        self,
        directory: str | Path,
        pattern: str = "**/*.twb",
    ) -> int:
        """Index all workbooks in *directory* matching *pattern*.

        Args:
            directory: Root directory to scan.
            pattern: Glob pattern (default ``**/*.twb``).

        Returns:
            Number of workbooks successfully indexed.
        """
        directory = Path(directory)
        patterns = [pattern]
        if "*.twb" in pattern and "*.twbx" not in pattern:
            patterns.append(pattern.replace("*.twb", "*.twbx"))

        count = 0
        paths: set[Path] = set()
        for pat in patterns:
            paths.update(directory.glob(pat))

        for p in sorted(paths):
            try:
                self.add(p)
                count += 1
            except Exception:  # noqa: BLE001
                pass
        return count

    def remove(self, path: str | Path) -> None:
        """Remove a workbook and its associated records from the index.

        Args:
            path: Path that was previously indexed.
        """
        path = str(Path(path).resolve())
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT id FROM workbooks WHERE path = ?", (path,)
        ).fetchone()
        if row:
            wb_id = row[0]
            cur.execute("DELETE FROM fields WHERE workbook_id = ?", (wb_id,))
            cur.execute("DELETE FROM connections WHERE workbook_id = ?", (wb_id,))
            cur.execute("DELETE FROM workbooks WHERE id = ?", (wb_id,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def search_field(self, name: str, *, exact: bool = False) -> list[dict[str, Any]]:
        """Search for fields by caption.

        Args:
            name: Search term.
            exact: When ``True``, match exact caption (case-insensitive).
                   When ``False``, perform a substring search.

        Returns:
            List of dicts with keys: ``workbook``, ``datasource``, ``caption``,
            ``formula``, ``is_calculated``.
        """
        cur = self._conn.cursor()
        if exact:
            rows = cur.execute(
                "SELECT w.path, f.datasource, f.caption, f.formula, f.is_calculated"
                " FROM fields f JOIN workbooks w ON f.workbook_id = w.id"
                " WHERE lower(f.caption) = lower(?)",
                (name,),
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT w.path, f.datasource, f.caption, f.formula, f.is_calculated"
                " FROM fields f JOIN workbooks w ON f.workbook_id = w.id"
                " WHERE lower(f.caption) LIKE lower(?)",
                (f"%{name}%",),
            ).fetchall()
        return [
            {
                "workbook": r["path"],
                "datasource": r["datasource"],
                "caption": r["caption"],
                "formula": r["formula"],
                "is_calculated": bool(r["is_calculated"]),
            }
            for r in rows
        ]

    def search_connection(self, term: str) -> list[dict[str, Any]]:
        """Search connections by server name, dbname, or class.

        Args:
            term: Substring to search for.

        Returns:
            List of dicts with keys: ``workbook``, ``datasource``, ``class_``,
            ``server``, ``dbname``.
        """
        cur = self._conn.cursor()
        like = f"%{term}%"
        rows = cur.execute(
            "SELECT w.path, c.datasource, c.class_, c.server, c.dbname"
            " FROM connections c JOIN workbooks w ON c.workbook_id = w.id"
            " WHERE lower(c.server) LIKE lower(?)"
            "    OR lower(c.dbname) LIKE lower(?)"
            "    OR lower(c.class_) LIKE lower(?)",
            (like, like, like),
        ).fetchall()
        return [
            {
                "workbook": r["path"],
                "datasource": r["datasource"],
                "class_": r["class_"],
                "server": r["server"],
                "dbname": r["dbname"],
            }
            for r in rows
        ]

    def all_workbooks(self) -> list[dict[str, Any]]:
        """Return all indexed workbooks.

        Returns:
            List of dicts with keys: ``path``, ``version``, ``indexed_at``.
        """
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT path, version, indexed_at FROM workbooks ORDER BY path"
        ).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict[str, int]:
        """Return high-level index statistics.

        Returns:
            Dict with keys: ``workbooks``, ``fields``, ``calculated_fields``,
            ``connections``.
        """
        cur = self._conn.cursor()
        workbooks = cur.execute("SELECT COUNT(*) FROM workbooks").fetchone()[0]
        fields = cur.execute("SELECT COUNT(*) FROM fields").fetchone()[0]
        calc_fields = cur.execute(
            "SELECT COUNT(*) FROM fields WHERE is_calculated = 1"
        ).fetchone()[0]
        connections = cur.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
        return {
            "workbooks": workbooks,
            "fields": fields,
            "calculated_fields": calc_fields,
            "connections": connections,
        }
