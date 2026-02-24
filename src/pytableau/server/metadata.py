"""Tableau Metadata API (GraphQL) client.

Requires the ``requests`` library (included in ``[server]`` optional extra)::

    pip install "pytableau[server]"

Usage::

    from pytableau.server.metadata import MetadataClient

    client = MetadataClient("https://my-tableau-server", auth_token)
    result = client.fields_for_datasource("Superstore")
    for field in result.fields:
        print(field.name, field.data_type)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pytableau._compat import import_optional

_requests = import_optional("requests", "server")


@dataclass
class MetadataField:
    """A single field returned from the Metadata API."""

    id: str
    name: str
    datasource: str
    data_type: str | None = None


@dataclass
class MetadataQueryResult:
    """Result of a Metadata API query."""

    fields: list[MetadataField] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# GraphQL query templates
# ---------------------------------------------------------------------------

_FIELDS_FOR_DATASOURCE_QUERY = """
query FieldsForDatasource($name: String!) {
  publishedDatasourcesConnection(filter: {name: $name}) {
    nodes {
      id
      name
      fields {
        id
        name
        dataType
      }
    }
  }
}
"""

_WORKBOOK_LINEAGE_QUERY = """
query WorkbookLineage($luid: String!) {
  workbooks(filter: {luid: $luid}) {
    id
    name
    upstreamDatasources {
      id
      name
    }
    downstreamWorkbooks {
      id
      name
    }
  }
}
"""

_SEARCH_FIELDS_QUERY = """
query SearchFields($nameContains: String!) {
  fieldsConnection(filter: {name: {contains: $nameContains}}) {
    nodes {
      id
      name
      dataType
      datasource {
        id
        name
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# MetadataClient
# ---------------------------------------------------------------------------


class MetadataClient:
    """Thin GraphQL client for the Tableau Metadata API.

    Args:
        server_url: Base URL of the Tableau Server (e.g. ``https://my-server``).
        token: Active Tableau REST API auth token (from a sign-in response).
    """

    def __init__(self, server_url: str, token: str) -> None:
        self._url = server_url.rstrip("/") + "/api/metadata/graphql"
        self._headers = {
            "x-tableau-auth": token,
            "content-type": "application/json",
        }

    def query(self, gql: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a raw GraphQL query against the Metadata API.

        Args:
            gql: GraphQL query string.
            variables: Optional variables dict.

        Returns:
            Parsed JSON response.

        Raises:
            ImportError: If the ``requests`` library is not installed.
            requests.HTTPError: On non-2xx HTTP responses.
        """
        from pytableau._compat import _MissingDependency

        if isinstance(_requests, _MissingDependency):
            raise ImportError(str(_requests))

        payload: dict[str, Any] = {"query": gql}
        if variables:
            payload["variables"] = variables

        resp = _requests.post(
            self._url,
            json=payload,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def fields_for_datasource(self, datasource_name: str) -> MetadataQueryResult:
        """Query all fields for a published datasource by name.

        Args:
            datasource_name: Exact name of the published datasource.

        Returns:
            :class:`MetadataQueryResult` with parsed fields.
        """
        raw = self.query(_FIELDS_FOR_DATASOURCE_QUERY, {"name": datasource_name})
        fields: list[MetadataField] = []
        nodes = raw.get("data", {}).get("publishedDatasourcesConnection", {}).get("nodes", [])
        for ds_node in nodes:
            ds_name = ds_node.get("name", "")
            for f in ds_node.get("fields", []):
                fields.append(
                    MetadataField(
                        id=f.get("id", ""),
                        name=f.get("name", ""),
                        datasource=ds_name,
                        data_type=f.get("dataType"),
                    )
                )
        return MetadataQueryResult(fields=fields, raw=raw)

    def workbook_lineage(self, workbook_luid: str) -> dict[str, Any]:
        """Get upstream/downstream lineage for a workbook by LUID.

        Args:
            workbook_luid: The workbook's LUID identifier.

        Returns:
            Raw dict with ``upstreamDatasources`` and ``downstreamWorkbooks`` lists.
        """
        raw = self.query(_WORKBOOK_LINEAGE_QUERY, {"luid": workbook_luid})
        workbooks = raw.get("data", {}).get("workbooks", [])
        if workbooks:
            return workbooks[0]
        return {}

    def search_fields(self, name_contains: str) -> MetadataQueryResult:
        """Search across all datasources for fields whose name contains *name_contains*.

        Args:
            name_contains: Substring to search for in field names.

        Returns:
            :class:`MetadataQueryResult` with matching fields.
        """
        raw = self.query(_SEARCH_FIELDS_QUERY, {"nameContains": name_contains})
        fields: list[MetadataField] = []
        nodes = raw.get("data", {}).get("fieldsConnection", {}).get("nodes", [])
        for f in nodes:
            ds = f.get("datasource") or {}
            fields.append(
                MetadataField(
                    id=f.get("id", ""),
                    name=f.get("name", ""),
                    datasource=ds.get("name", ""),
                    data_type=f.get("dataType"),
                )
            )
        return MetadataQueryResult(fields=fields, raw=raw)
