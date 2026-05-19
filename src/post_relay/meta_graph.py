from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional
from urllib import parse, request, error


DEFAULT_META_GRAPH_BASE_URL = "https://graph.facebook.com"
DEFAULT_META_GRAPH_VERSION = "v19.0"


class MetaGraphConfigError(ValueError):
    """Raised when local Meta Graph configuration is incomplete."""


class MetaGraphRequestError(RuntimeError):
    """Raised when a Meta Graph read-only request fails."""


@dataclass(frozen=True)
class MetaGraphConfig:
    access_token: str
    page_id: Optional[str] = None
    instagram_account_id: Optional[str] = None
    base_url: str = DEFAULT_META_GRAPH_BASE_URL
    api_version: str = DEFAULT_META_GRAPH_VERSION

    def safe_summary(self) -> str:
        return (
            f"base_url={self.base_url}, api_version={self.api_version}, "
            f"page_id={self.page_id or '<unset>'}, "
            f"instagram_account_id={self.instagram_account_id or '<unset>'}, "
            "access_token=<redacted>"
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
        base_url=get("POST_RELAY_META_GRAPH_BASE_URL") or DEFAULT_META_GRAPH_BASE_URL,
        api_version=get("POST_RELAY_META_GRAPH_VERSION") or DEFAULT_META_GRAPH_VERSION,
    )


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

    def search_pages(self, *, query: str, fields: str = "id,name,location,link") -> Mapping[str, Any]:
        return self._request(
            "pages/search",
            {"q": query, "fields": fields},
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

    def _request(self, path: str, params: Mapping[str, str], *, method: str = "GET") -> Mapping[str, Any]:
        url = self._url(path)
        request_params = dict(params)
        request_params["access_token"] = self.config.access_token
        try:
            return self._transport(method, url, request_params)
        except MetaGraphRequestError as exc:
            raise MetaGraphRequestError(
                redact_secrets(str(exc), [self.config.access_token])
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive sanitization path
            raise MetaGraphRequestError(
                redact_secrets(str(exc), [self.config.access_token])
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
