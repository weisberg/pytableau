"""Server integration primitives for Tableau Server and Tableau Cloud."""

from __future__ import annotations

from pathlib import Path

from pytableau._compat import _MissingDependency, import_optional
from pytableau.exceptions import AuthenticationError, ServerError

_tsc = import_optional("tableauserverclient", "server")


def _require_server_module() -> object:
    if isinstance(_tsc, _MissingDependency):
        raise ImportError(str(_tsc))
    return _tsc


class ServerClient:
    """Thin adapter around :mod:`tableauserverclient`.

    The implementation keeps to a small, defensive surface area and defers to the
    upstream client for every transport-heavy operation.
    """

    def __init__(
        self,
        server_url: str,
        *,
        use_server_version: bool = True,
        site_id: str = "",
        **_: object,
    ) -> None:
        tsc = _require_server_module()
        server_ctor = tsc.Server
        self.server = server_ctor(server_url, use_server_version=use_server_version)
        self.site_id = site_id
        self._tsc = tsc
        self._signed_in = False

    def close(self) -> None:
        if not self._signed_in:
            return
        try:
            self.server.auth.sign_out()
        finally:
            self._signed_in = False

    def __enter__(self) -> ServerClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def sign_in_with_personal_access_token(
        self,
        token_name: str,
        token_secret: str,
        *,
        site_id: str | None = None,
    ) -> None:
        tsc = self._tsc
        auth_ctor = getattr(tsc, "PersonalAccessTokenAuth", None)
        if auth_ctor is None:
            raise AuthenticationError(
                "tableauserverclient does not expose PersonalAccessTokenAuth in this version"
            )
        sid = site_id if site_id is not None else self.site_id
        auth = auth_ctor(token_name, token_secret, sid)
        self._sign_in(auth)

    def sign_in_with_credentials(
        self,
        username: str,
        password: str,
        *,
        site_id: str | None = None,
    ) -> None:
        tsc = self._tsc
        auth_ctor = getattr(tsc, "TableauAuth", None)
        if auth_ctor is None:
            raise AuthenticationError(
                "tableauserverclient does not expose TableauAuth in this version"
            )
        sid = site_id if site_id is not None else self.site_id
        auth = auth_ctor(username, password, sid)
        self._sign_in(auth)

    def _ensure_signed_in(self, **auth: object) -> None:
        if self._signed_in:
            return
        if "token_name" in auth and "token_secret" in auth:
            self.sign_in_with_personal_access_token(
                str(auth["token_name"]),
                str(auth["token_secret"]),
                site_id=str(auth.get("site_id", self.site_id)),
            )
            return
        if "username" in auth and "password" in auth:
            self.sign_in_with_credentials(
                str(auth["username"]),
                str(auth["password"]),
                site_id=str(auth.get("site_id", self.site_id)),
            )
            return
        raise AuthenticationError(
            "Authentication credentials required: provide token_name/token_secret or username/password"
        )

    def _sign_in(self, auth: object) -> None:
        try:
            self.server.auth.sign_in(auth)
        except Exception as exc:  # pragma: no cover - client errors vary by deployment
            raise AuthenticationError("Failed to authenticate with Tableau Server/Cloud") from exc
        self._signed_in = True

    def publish_workbook(
        self,
        workbook: str | Path,
        *,
        project_id: str,
        name: str | None = None,
        overwrite: bool = True,
        **auth: object,
    ) -> object:
        workbook_path = Path(workbook).expanduser()
        if not workbook_path.exists():
            raise FileNotFoundError(f"Workbook not found: {workbook_path}")

        tsc = self._tsc
        if not self._signed_in:
            self._ensure_signed_in(**auth)

        workbook_item_ctor = getattr(tsc, "WorkbookItem", None)
        if workbook_item_ctor is None:
            workbook_item_ctor = getattr(getattr(tsc, "models", None), "WorkbookItem", None)
        if workbook_item_ctor is None:
            raise ServerError("Unable to construct WorkbookItem via tableauserverclient API")

        item = workbook_item_ctor(name or workbook_path.stem, project_id)
        publish = self.server.workbooks.publish
        mode = getattr(getattr(tsc, "PublishMode", None), "Overwrite", "Overwrite")
        if not overwrite:
            mode = getattr(getattr(tsc, "PublishMode", None), "CreateNew", "CreateNew")

        try:
            return publish(item, str(workbook_path), mode=mode)
        except TypeError:
            return publish(item, str(workbook_path))

    def download_workbook(
        self,
        workbook_id: str,
        *,
        destination: str | Path | None = None,
        **auth: object,
    ) -> Path:
        # download does not require credentials when called from an already-open session
        if not self._signed_in:
            self._ensure_signed_in(**auth)

        download_to = Path(destination).expanduser() if destination else None
        if download_to is None:
            raise ValueError("download destination is required")
        download_to.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.server.workbooks.download(workbook_id, filepath=str(download_to))
        except TypeError:
            try:
                self.server.workbooks.download(workbook_id, download_to)
            except TypeError as exc:
                raise ServerError("Unable to call tableauserverclient download() method") from exc
        return download_to
