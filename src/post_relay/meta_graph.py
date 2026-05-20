from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional
from urllib import parse, request, error


DEFAULT_META_GRAPH_BASE_URL = "https://graph.facebook.com"
DEFAULT_META_OAUTH_DIALOG_BASE_URL = "https://www.facebook.com"
DEFAULT_META_GRAPH_VERSION = "v19.0"
DEFAULT_META_OAUTH_SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
)


class MetaGraphConfigError(ValueError):
    """Raised when local Meta Graph configuration is incomplete."""


class MetaGraphRequestError(RuntimeError):
    """Raised when a Meta Graph read-only request fails."""


@dataclass(frozen=True)
class TokenExtensionResult:
    access_token: str
    token_type: Optional[str]
    expires_in: Optional[int]
    expires_at: Optional[datetime]

    def to_text(self, *, env_updated: bool) -> str:
        lines = [
            "Meta Graph user token extended",
            "Access token: <redacted>",
            f"Token type: {self.token_type or '<unknown>'}",
            f"Expires in: {self.expires_in if self.expires_in is not None else '<unknown>'} seconds",
            f"Expires at: {self.expires_at.isoformat() if self.expires_at else '<unknown>'}",
            f"Env file updated: {'yes' if env_updated else 'no'}",
            "Publishing endpoints called: no",
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class MetaGraphConfig:
    access_token: str
    page_id: Optional[str] = None
    instagram_account_id: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    base_url: str = DEFAULT_META_GRAPH_BASE_URL
    api_version: str = DEFAULT_META_GRAPH_VERSION

    def safe_summary(self) -> str:
        return (
            f"base_url={self.base_url}, api_version={self.api_version}, "
            f"page_id={self.page_id or '<unset>'}, "
            f"instagram_account_id={self.instagram_account_id or '<unset>'}, "
            f"app_id={'<set>' if self.app_id else '<unset>'}, "
            "access_token=<redacted>, app_secret=<redacted>"
        )


@dataclass(frozen=True)
class ReadOnlyValidationResult:
    page_id: str
    page_name: Optional[str]
    instagram_account_id: str
    instagram_username: Optional[str]
    instagram_account_type: Optional[str]
    instagram_media_count: Optional[int]

    def to_text(self) -> str:
        return "\n".join(
            [
                "Meta Graph read-only validation",
                f"Page: {self.page_name or '<unknown>'} ({self.page_id})",
                f"Instagram account: {self.instagram_username or '<unknown>'} ({self.instagram_account_id})",
                f"Account type: {self.instagram_account_type or '<unknown>'}",
                f"Media count: {self.instagram_media_count if self.instagram_media_count is not None else '<unknown>'}",
                "Publishing endpoints called: no",
            ]
        )


@dataclass(frozen=True)
class DiscoveredMetaAccount:
    page_id: str
    page_name: Optional[str]
    instagram_account_id: Optional[str]
    instagram_username: Optional[str]
    instagram_media_count: Optional[int]


@dataclass(frozen=True)
class AccountDiscoveryResult:
    pages: list[DiscoveredMetaAccount]
    publishing_endpoints_called: bool = False

    def to_text(self, *, env_updated: bool = False) -> str:
        lines = ["Meta Graph account discovery"]
        if not self.pages:
            lines.append("No visible Facebook Pages were returned.")
        for index, page in enumerate(self.pages, start=1):
            lines.append(f"{index}. Page: {page.page_name or '<unknown>'} ({page.page_id})")
            if page.instagram_account_id:
                lines.append(
                    f"   Instagram account: {page.instagram_username or '<unknown>'} ({page.instagram_account_id})"
                )
                lines.append(
                    f"   Media count: {page.instagram_media_count if page.instagram_media_count is not None else '<unknown>'}"
                )
            else:
                lines.append("   Instagram account: <not linked or not visible>")
        lines.append(f"Env file updated: {'yes' if env_updated else 'no'}")
        lines.append(
            f"Publishing endpoints called: {'yes' if self.publishing_endpoints_called else 'no'}"
        )
        return "\n".join(lines)


Transport = Callable[[str, str, Mapping[str, str]], Mapping[str, Any]]


def load_meta_graph_config(env_file: Optional[Path] = Path(".env")) -> MetaGraphConfig:
    values = _read_env_file(env_file) if env_file is not None else {}

    def get(name: str) -> Optional[str]:
        return os.environ.get(name) or values.get(name)

    access_token = get("POST_RELAY_USER_ACCESS_TOKEN")
    if not access_token:
        raise MetaGraphConfigError(
            "POST_RELAY_USER_ACCESS_TOKEN is required in the environment or private .env file"
        )

    return MetaGraphConfig(
        access_token=access_token,
        page_id=get("POST_RELAY_FACEBOOK_PAGE_ID"),
        instagram_account_id=get("POST_RELAY_INSTAGRAM_ACCOUNT_ID"),
        app_id=get("POST_RELAY_META_APP_ID"),
        app_secret=get("POST_RELAY_META_APP_SECRET"),
        base_url=get("POST_RELAY_META_GRAPH_BASE_URL") or DEFAULT_META_GRAPH_BASE_URL,
        api_version=get("POST_RELAY_META_GRAPH_VERSION") or DEFAULT_META_GRAPH_VERSION,
    )


def load_meta_oauth_config(
    env_file: Optional[Path] = Path(".env"),
    *,
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
) -> MetaGraphConfig:
    values = _read_env_file(env_file) if env_file is not None else {}

    def get(name: str) -> Optional[str]:
        return os.environ.get(name) or values.get(name)

    resolved_app_id = app_id or get("POST_RELAY_META_APP_ID")
    resolved_app_secret = app_secret or get("POST_RELAY_META_APP_SECRET")
    if not resolved_app_id or not resolved_app_secret:
        raise MetaGraphConfigError(
            "POST_RELAY_META_APP_ID and POST_RELAY_META_APP_SECRET are required for Meta OAuth login"
        )
    return MetaGraphConfig(
        access_token=get("POST_RELAY_USER_ACCESS_TOKEN") or "",
        page_id=get("POST_RELAY_FACEBOOK_PAGE_ID"),
        instagram_account_id=get("POST_RELAY_INSTAGRAM_ACCOUNT_ID"),
        app_id=resolved_app_id,
        app_secret=resolved_app_secret,
        base_url=get("POST_RELAY_META_GRAPH_BASE_URL") or DEFAULT_META_GRAPH_BASE_URL,
        api_version=get("POST_RELAY_META_GRAPH_VERSION") or DEFAULT_META_GRAPH_VERSION,
    )


def build_meta_oauth_authorization_url(
    config: MetaGraphConfig,
    *,
    redirect_uri: str,
    state: str,
    scopes: Iterable[str] = DEFAULT_META_OAUTH_SCOPES,
) -> str:
    if not config.app_id:
        raise MetaGraphConfigError("POST_RELAY_META_APP_ID is required for Meta OAuth login")
    params = parse.urlencode(
        {
            "client_id": config.app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(scopes),
            "response_type": "code",
        }
    )
    return f"{DEFAULT_META_OAUTH_DIALOG_BASE_URL}/{config.api_version}/dialog/oauth?{params}"


def redact_secrets(text: str, secrets: Iterable[Optional[str]]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted


class MetaGraphClient:
    """Small read-only Meta Graph client for account/linkage validation."""

    def __init__(self, config: MetaGraphConfig, transport: Optional[Transport] = None) -> None:
        self.config = config
        self._transport = transport or _urllib_json_transport

    def list_pages(self) -> Mapping[str, Any]:
        return self._request("me/accounts", {})

    def get_page_with_instagram_account(self, page_id: str) -> Mapping[str, Any]:
        return self._request(
            page_id,
            {"fields": "id,name,instagram_business_account"},
        )

    def get_instagram_account(self, instagram_account_id: str) -> Mapping[str, Any]:
        return self._request(
            instagram_account_id,
            {"fields": "id,username,media_count"},
        )

    def get_instagram_account_metrics(self, instagram_account_id: str) -> Mapping[str, Any]:
        return self._request(
            instagram_account_id,
            {"fields": "id,username,followers_count,follows_count,media_count"},
        )

    def search_pages(self, *, query: str, fields: str = "id,name,location,link") -> Mapping[str, Any]:
        return self._request(
            "pages/search",
            {"q": query, "fields": fields},
        )

    def get_media_insights(self, media_id: str, *, metrics: Iterable[str]) -> Mapping[str, Any]:
        return self._request(
            f"{media_id}/insights",
            {"metric": ",".join(metrics)},
        )

    def discover_accounts(self) -> AccountDiscoveryResult:
        pages_payload = self.list_pages()
        discovered: list[DiscoveredMetaAccount] = []
        for page in pages_payload.get("data") or []:
            page_id = str(page.get("id") or "")
            if not page_id:
                continue
            page_name = str(page.get("name")) if page.get("name") else None
            page_payload = self.get_page_with_instagram_account(page_id)
            linked = page_payload.get("instagram_business_account") or {}
            linked_id = linked.get("id")
            if not linked_id:
                discovered.append(
                    DiscoveredMetaAccount(
                        page_id=page_id,
                        page_name=str(page_payload.get("name") or page_name) if page_payload.get("name") or page_name else None,
                        instagram_account_id=None,
                        instagram_username=None,
                        instagram_media_count=None,
                    )
                )
                continue
            instagram_payload = self.get_instagram_account(str(linked_id))
            discovered.append(
                DiscoveredMetaAccount(
                    page_id=page_id,
                    page_name=str(page_payload.get("name") or page_name) if page_payload.get("name") or page_name else None,
                    instagram_account_id=str(instagram_payload.get("id") or linked_id),
                    instagram_username=str(instagram_payload.get("username")) if instagram_payload.get("username") else None,
                    instagram_media_count=_optional_int(instagram_payload.get("media_count")),
                )
            )
        return AccountDiscoveryResult(pages=discovered, publishing_endpoints_called=False)

    def discovery_dry_run_urls(self) -> list[str]:
        return [
            self._url("me/accounts") + "?access_token=<redacted>",
            self._url("<page_id>") + "?fields=id,name,instagram_business_account&access_token=<redacted>",
            self._url("<instagram_account_id>") + "?fields=id,username,media_count&access_token=<redacted>",
        ]

    def exchange_oauth_authorization_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        now: Optional[datetime] = None,
    ) -> TokenExtensionResult:
        if not self.config.app_id or not self.config.app_secret:
            raise MetaGraphConfigError(
                "POST_RELAY_META_APP_ID and POST_RELAY_META_APP_SECRET are required for Meta OAuth login"
            )
        payload = self._request(
            "oauth/access_token",
            {
                "client_id": self.config.app_id,
                "client_secret": self.config.app_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
            include_access_token=False,
        )
        access_token = payload.get("access_token")
        if not access_token:
            raise MetaGraphRequestError("Meta Graph did not return a user access token")
        expires_in = _optional_int(payload.get("expires_in"))
        issued_at = now or datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=expires_in) if expires_in is not None else None
        return TokenExtensionResult(
            access_token=str(access_token),
            token_type=str(payload.get("token_type")) if payload.get("token_type") else None,
            expires_in=expires_in,
            expires_at=expires_at,
        )

    def exchange_long_lived_user_token(self, *, now: Optional[datetime] = None) -> TokenExtensionResult:
        if not self.config.app_id or not self.config.app_secret:
            raise MetaGraphConfigError(
                "POST_RELAY_META_APP_ID and POST_RELAY_META_APP_SECRET are required to extend a Meta user token"
            )
        payload = self._request(
            "oauth/access_token",
            {
                "grant_type": "fb_exchange_token",
                "client_id": self.config.app_id,
                "client_secret": self.config.app_secret,
                "fb_exchange_token": self.config.access_token,
            },
            include_access_token=False,
        )
        access_token = payload.get("access_token")
        if not access_token:
            raise MetaGraphRequestError("Meta Graph did not return an extended access token")
        expires_in = _optional_int(payload.get("expires_in"))
        issued_at = now or datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=expires_in) if expires_in is not None else None
        return TokenExtensionResult(
            access_token=str(access_token),
            token_type=str(payload.get("token_type")) if payload.get("token_type") else None,
            expires_in=expires_in,
            expires_at=expires_at,
        )

    def create_image_container(
        self,
        instagram_account_id: str,
        *,
        image_url: str,
        caption: str,
        location_id: Optional[str] = None,
    ) -> Mapping[str, Any]:
        params = {"image_url": image_url, "caption": caption}
        if location_id:
            params["location_id"] = location_id
        return self._request(
            f"{instagram_account_id}/media",
            params,
            method="POST",
        )

    def create_carousel_item_container(
        self,
        instagram_account_id: str,
        *,
        image_url: str,
    ) -> Mapping[str, Any]:
        return self._request(
            f"{instagram_account_id}/media",
            {"image_url": image_url, "is_carousel_item": "true"},
            method="POST",
        )

    def create_carousel_container(
        self,
        instagram_account_id: str,
        *,
        child_container_ids: Iterable[str],
        caption: str,
        location_id: Optional[str] = None,
    ) -> Mapping[str, Any]:
        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(child_container_ids),
            "caption": caption,
        }
        if location_id:
            params["location_id"] = location_id
        return self._request(
            f"{instagram_account_id}/media",
            params,
            method="POST",
        )

    def get_media_container_status(self, container_id: str) -> Mapping[str, Any]:
        return self._request(container_id, {"fields": "id,status_code"})

    def publish_media(self, instagram_account_id: str, *, creation_id: str) -> Mapping[str, Any]:
        return self._request(
            f"{instagram_account_id}/media_publish",
            {"creation_id": creation_id},
            method="POST",
        )

    def validate_readonly_access(self) -> ReadOnlyValidationResult:
        pages_payload = self.list_pages()
        page = _select_page(pages_payload, self.config.page_id)
        page_id = str(page["id"])

        page_payload = self.get_page_with_instagram_account(page_id)
        instagram_account_id = _resolve_instagram_account_id(
            page_payload, self.config.instagram_account_id
        )
        instagram_payload = self.get_instagram_account(instagram_account_id)

        return ReadOnlyValidationResult(
            page_id=page_id,
            page_name=page_payload.get("name") or page.get("name"),
            instagram_account_id=str(instagram_payload.get("id") or instagram_account_id),
            instagram_username=instagram_payload.get("username"),
            instagram_account_type=instagram_payload.get("account_type"),
            instagram_media_count=instagram_payload.get("media_count"),
        )

    def dry_run_urls(self) -> list[str]:
        page_id = self.config.page_id or "<page_id_from_/me/accounts>"
        instagram_account_id = self.config.instagram_account_id or "<instagram_account_id_from_page>"
        return [
            self._url("me/accounts"),
            self._url(page_id) + "?fields=id,name,instagram_business_account&access_token=<redacted>",
            self._url(instagram_account_id) + "?fields=id,username,media_count&access_token=<redacted>",
        ]

    def _request(
        self,
        path: str,
        params: Mapping[str, str],
        *,
        method: str = "GET",
        include_access_token: bool = True,
    ) -> Mapping[str, Any]:
        url = self._url(path)
        request_params = dict(params)
        if include_access_token:
            request_params["access_token"] = self.config.access_token
        try:
            return self._transport(method, url, request_params)
        except MetaGraphRequestError as exc:
            raise MetaGraphRequestError(
                redact_secrets(str(exc), [self.config.access_token, self.config.app_secret])
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive sanitization path
            raise MetaGraphRequestError(
                redact_secrets(str(exc), [self.config.access_token, self.config.app_secret])
            ) from exc

    def _url(self, path: str) -> str:
        normalized_path = path.strip("/")
        return f"{self.config.base_url.rstrip('/')}/{self.config.api_version}/{normalized_path}"


def _select_page(pages_payload: Mapping[str, Any], preferred_page_id: Optional[str]) -> Mapping[str, Any]:
    pages = pages_payload.get("data") or []
    if not pages:
        raise MetaGraphRequestError("Meta Graph returned no visible Facebook Pages")
    if preferred_page_id is None:
        return pages[0]
    for page in pages:
        if str(page.get("id")) == preferred_page_id:
            return page
    raise MetaGraphRequestError(f"Configured Facebook Page ID {preferred_page_id} was not visible")


def _resolve_instagram_account_id(
    page_payload: Mapping[str, Any], configured_instagram_account_id: Optional[str]
) -> str:
    linked = page_payload.get("instagram_business_account") or {}
    linked_id = linked.get("id")
    if configured_instagram_account_id and linked_id and configured_instagram_account_id != str(linked_id):
        raise MetaGraphRequestError(
            "Configured Instagram Account ID does not match the Page-linked account"
        )
    if configured_instagram_account_id:
        return configured_instagram_account_id
    if linked_id:
        return str(linked_id)
    raise MetaGraphRequestError("Facebook Page did not include a linked Instagram account")


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def update_meta_graph_oauth_env_file(
    env_file: Path,
    *,
    access_token: str,
    page_id: Optional[str] = None,
    instagram_account_id: Optional[str] = None,
) -> None:
    replacements = {"POST_RELAY_USER_ACCESS_TOKEN": access_token}
    if page_id:
        replacements["POST_RELAY_FACEBOOK_PAGE_ID"] = page_id
    if instagram_account_id:
        replacements["POST_RELAY_INSTAGRAM_ACCOUNT_ID"] = instagram_account_id
    _update_env_values(env_file, replacements)


def update_meta_graph_account_ids_env_file(env_file: Path, *, page_id: str, instagram_account_id: str) -> None:
    _update_env_values(
        env_file,
        {
            "POST_RELAY_FACEBOOK_PAGE_ID": page_id,
            "POST_RELAY_INSTAGRAM_ACCOUNT_ID": instagram_account_id,
        },
    )


def update_meta_graph_access_token_env_file(env_file: Path, new_access_token: str) -> None:
    _update_env_values(env_file, {"POST_RELAY_USER_ACCESS_TOKEN": new_access_token})


def _update_env_values(env_file: Path, replacements: Mapping[str, str]) -> None:
    existing = env_file.read_text() if env_file.exists() else ""
    lines = existing.splitlines(keepends=True)
    updated_lines: list[str] = []
    remaining = dict(replacements)
    for line in lines:
        stripped = line.lstrip()
        matched_key = next((key for key in remaining if stripped.startswith(f"{key}=")), None)
        if matched_key:
            newline = "\n" if line.endswith("\n") else ""
            prefix = line[: len(line) - len(stripped)]
            updated_lines.append(f"{prefix}{matched_key}={remaining.pop(matched_key)}{newline}")
        else:
            updated_lines.append(line)
    for key, value in remaining.items():
        separator = "" if not existing or (updated_lines and updated_lines[-1].endswith("\n")) else "\n"
        updated_lines.append(f"{separator}{key}={value}\n")
    tmp_file = env_file.with_name(f"{env_file.name}.tmp")
    tmp_file.write_text("".join(updated_lines))
    tmp_file.replace(env_file)


def _read_env_file(env_file: Optional[Path]) -> Dict[str, str]:
    if env_file is None or not env_file.exists():
        return {}
    values: Dict[str, str] = {}
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _strip_optional_quotes(value.strip())
    return values


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _urllib_json_transport(method: str, url: str, params: Mapping[str, str]) -> Mapping[str, Any]:
    query = parse.urlencode(params).encode("utf-8")
    if method == "GET":
        request_url = f"{url}?{query.decode('utf-8')}"
        graph_request = request.Request(request_url, method="GET")
    elif method == "POST":
        graph_request = request.Request(url, data=query, method="POST")
        graph_request.add_header("Content-Type", "application/x-www-form-urlencoded")
    else:
        raise MetaGraphRequestError(f"Unsupported Meta Graph HTTP method: {method}")
    try:
        with request.urlopen(graph_request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise MetaGraphRequestError(f"Meta Graph HTTP {exc.code}: {payload}") from exc
    except error.URLError as exc:
        raise MetaGraphRequestError(f"Meta Graph request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MetaGraphRequestError("Meta Graph returned non-JSON response") from exc
    if isinstance(parsed, dict) and "error" in parsed:
        raise MetaGraphRequestError(f"Meta Graph error: {parsed['error']}")
    return parsed
