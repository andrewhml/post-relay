from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

import post_relay.cli as cli_module
from post_relay.cli import app
from post_relay.meta_graph import (
    MetaGraphClient,
    MetaGraphConfig,
    MetaGraphConfigError,
    MetaGraphRequestError,
    ReadOnlyValidationResult,
    load_meta_graph_config,
    redact_secrets,
    update_meta_graph_access_token_env_file,
)

runner = CliRunner()


def test_load_meta_graph_config_reads_env_file_without_logging_secret(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POST_RELAY_USER_ACCESS_TOKEN=env-file-token",
                "POST_RELAY_FACEBOOK_PAGE_ID=998312870038313",
                "POST_RELAY_INSTAGRAM_ACCOUNT_ID=17841400498120050",
                "POST_RELAY_META_GRAPH_BASE_URL=https://graph.facebook.com",
                "POST_RELAY_META_GRAPH_VERSION=v19.0",
                "POST_RELAY_META_APP_ID=app-id-123",
                "POST_RELAY_META_APP_SECRET=app-secret-456",
            ]
        )
    )
    monkeypatch.delenv("POST_RELAY_USER_ACCESS_TOKEN", raising=False)

    config = load_meta_graph_config(env_file=env_file)

    assert config.access_token == "env-file-token"
    assert config.page_id == "998312870038313"
    assert config.instagram_account_id == "17841400498120050"
    assert config.base_url == "https://graph.facebook.com"
    assert config.api_version == "v19.0"
    assert config.app_id == "app-id-123"
    assert config.app_secret == "app-secret-456"
    assert "env-file-token" not in config.safe_summary()
    assert "app-secret-456" not in config.safe_summary()
    assert "<redacted>" in config.safe_summary()


def test_environment_variables_override_env_file_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("POST_RELAY_USER_ACCESS_TOKEN=env-file-token\n")
    monkeypatch.setenv("POST_RELAY_USER_ACCESS_TOKEN", "environment-token")

    config = load_meta_graph_config(env_file=env_file)

    assert config.access_token == "environment-token"


def test_load_meta_graph_config_requires_access_token(monkeypatch):
    monkeypatch.delenv("POST_RELAY_USER_ACCESS_TOKEN", raising=False)

    with pytest.raises(MetaGraphConfigError) as error:
        load_meta_graph_config(env_file=None)

    assert "POST_RELAY_USER_ACCESS_TOKEN" in str(error.value)


def test_redact_secrets_removes_token_and_app_secret_from_errors():
    redacted = redact_secrets(
        "token abc123 and app secret shhh appear here",
        ["abc123", "shhh", ""],
    )

    assert "abc123" not in redacted
    assert "shhh" not in redacted
    assert redacted.count("<redacted>") == 2


def test_meta_graph_client_builds_readonly_account_requests_without_publishing():
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        if url.endswith("/me/accounts"):
            return {"data": [{"id": "998312870038313", "name": "Andrewhml"}]}
        if url.endswith("/998312870038313"):
            return {
                "id": "998312870038313",
                "name": "Andrewhml",
                "instagram_business_account": {"id": "17841400498120050"},
            }
        if url.endswith("/17841400498120050"):
            return {
                "id": "17841400498120050",
                "username": "andrewhml",
                "media_count": 722,
            }
        raise AssertionError(f"unexpected URL: {url}")

    client = MetaGraphClient(
        MetaGraphConfig(
            access_token="secret-token",
            page_id="998312870038313",
            instagram_account_id="17841400498120050",
        ),
        transport=fake_transport,
    )

    result = client.validate_readonly_access()

    assert result == ReadOnlyValidationResult(
        page_id="998312870038313",
        page_name="Andrewhml",
        instagram_account_id="17841400498120050",
        instagram_username="andrewhml",
        instagram_account_type=None,
        instagram_media_count=722,
    )
    assert [method for method, _url, _params in requested] == ["GET", "GET", "GET"]
    assert [url for _method, url, _params in requested] == [
        "https://graph.facebook.com/v19.0/me/accounts",
        "https://graph.facebook.com/v19.0/998312870038313",
        "https://graph.facebook.com/v19.0/17841400498120050",
    ]
    assert all(params["access_token"] == "secret-token" for _method, _url, params in requested)
    assert requested[1][2]["fields"] == "id,name,instagram_business_account"
    assert requested[2][2]["fields"] == "id,username,media_count"


def test_meta_graph_client_redacts_token_from_request_errors():
    def fake_transport(_method, _url, _params):
        raise MetaGraphRequestError("bad token secret-token")

    client = MetaGraphClient(
        MetaGraphConfig(access_token="secret-token"),
        transport=fake_transport,
    )

    with pytest.raises(MetaGraphRequestError) as error:
        client.list_pages()

    assert "secret-token" not in str(error.value)
    assert "<redacted>" in str(error.value)


def test_meta_graph_client_exchanges_user_token_without_publishing_or_leaking_secrets():
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        return {
            "access_token": "new-long-lived-token",
            "token_type": "bearer",
            "expires_in": 5183944,
        }

    client = MetaGraphClient(
        MetaGraphConfig(
            access_token="short-lived-token",
            app_id="app-id-123",
            app_secret="app-secret-456",
        ),
        transport=fake_transport,
    )

    result = client.exchange_long_lived_user_token(
        now=datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    )

    assert result.access_token == "new-long-lived-token"
    assert result.token_type == "bearer"
    assert result.expires_in == 5183944
    assert result.expires_at.isoformat() == "2026-07-18T09:59:04+00:00"
    assert requested == [
        (
            "GET",
            "https://graph.facebook.com/v19.0/oauth/access_token",
            {
                "grant_type": "fb_exchange_token",
                "client_id": "app-id-123",
                "client_secret": "app-secret-456",
                "fb_exchange_token": "short-lived-token",
            },
        )
    ]
    rendered = result.to_text(env_updated=False)
    assert "new-long-lived-token" not in rendered
    assert "Meta Graph user token extended" in rendered
    assert "Env file updated: no" in rendered
    assert "Publishing endpoints called: no" in rendered


def test_meta_graph_client_token_exchange_requires_app_credentials():
    client = MetaGraphClient(MetaGraphConfig(access_token="short-lived-token"))

    with pytest.raises(MetaGraphConfigError) as error:
        client.exchange_long_lived_user_token()

    assert "POST_RELAY_META_APP_ID" in str(error.value)
    assert "POST_RELAY_META_APP_SECRET" in str(error.value)


def test_meta_graph_client_token_exchange_redacts_old_token_and_app_secret_from_errors():
    def fake_transport(_method, _url, _params):
        raise MetaGraphRequestError("bad short-lived-token and app-secret-456")

    client = MetaGraphClient(
        MetaGraphConfig(
            access_token="short-lived-token",
            app_id="app-id-123",
            app_secret="app-secret-456",
        ),
        transport=fake_transport,
    )

    with pytest.raises(MetaGraphRequestError) as error:
        client.exchange_long_lived_user_token()

    assert "short-lived-token" not in str(error.value)
    assert "app-secret-456" not in str(error.value)
    assert str(error.value).count("<redacted>") == 2


def test_update_meta_graph_access_token_env_file_replaces_only_user_token(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# private config\n"
        "POST_RELAY_META_APP_ID=app-id-123\n"
        "POST_RELAY_USER_ACCESS_TOKEN=old-token\n"
        "POST_RELAY_TEST_CAPTION=caption with spaces\n"
    )

    update_meta_graph_access_token_env_file(env_file, "new-token")

    assert env_file.read_text() == (
        "# private config\n"
        "POST_RELAY_META_APP_ID=app-id-123\n"
        "POST_RELAY_USER_ACCESS_TOKEN=new-token\n"
        "POST_RELAY_TEST_CAPTION=caption with spaces\n"
    )


def test_meta_token_extend_cli_requires_execute_for_network_and_does_not_print_secrets(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POST_RELAY_META_APP_ID=app-id-123\n"
        "POST_RELAY_META_APP_SECRET=app-secret-456\n"
        "POST_RELAY_USER_ACCESS_TOKEN=short-lived-token\n"
    )

    result = runner.invoke(app, ["meta", "token-extend", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert "Meta Graph user token extension (dry run)" in result.output
    assert "https://graph.facebook.com/v19.0/oauth/access_token" in result.output
    assert "No network calls were made." in result.output
    assert "short-lived-token" not in result.output
    assert "app-secret-456" not in result.output
    assert "POST_RELAY_USER_ACCESS_TOKEN=short-lived-token" in env_file.read_text()


def test_meta_token_extend_cli_updates_env_only_when_requested(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POST_RELAY_META_APP_ID=app-id-123\n"
        "POST_RELAY_META_APP_SECRET=app-secret-456\n"
        "POST_RELAY_USER_ACCESS_TOKEN=short-lived-token\n"
    )

    class FakeClient:
        def __init__(self, config):
            assert config.access_token == "short-lived-token"

        def exchange_long_lived_user_token(self):
            return cli_module.TokenExtensionResult(
                access_token="new-long-lived-token",
                token_type="bearer",
                expires_in=5183944,
                expires_at=datetime(2026, 7, 18, 10, 39, 4, tzinfo=timezone.utc),
            )

    monkeypatch.setattr(cli_module, "MetaGraphClient", FakeClient)

    result = runner.invoke(
        app,
        ["meta", "token-extend", "--env-file", str(env_file), "--execute", "--update-env"],
    )

    assert result.exit_code == 0
    assert "Meta Graph user token extended" in result.output
    assert "Env file updated: yes" in result.output
    assert "new-long-lived-token" not in result.output
    assert "app-secret-456" not in result.output
    assert "POST_RELAY_USER_ACCESS_TOKEN=new-long-lived-token" in env_file.read_text()


def test_meta_graph_client_discovers_visible_pages_and_linked_instagram_accounts_without_publishing():
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        if url.endswith("/me/accounts"):
            return {
                "data": [
                    {"id": "page-1", "name": "Travel Page"},
                    {"id": "page-2", "name": "No IG Page"},
                ]
            }
        if url.endswith("/page-1"):
            return {
                "id": "page-1",
                "name": "Travel Page",
                "instagram_business_account": {"id": "ig-1"},
            }
        if url.endswith("/page-2"):
            return {"id": "page-2", "name": "No IG Page"}
        if url.endswith("/ig-1"):
            return {"id": "ig-1", "username": "travel_creator", "media_count": 42}
        raise AssertionError(f"unexpected URL: {url}")

    client = MetaGraphClient(MetaGraphConfig(access_token="secret-token"), transport=fake_transport)

    result = client.discover_accounts()
    rendered = result.to_text()

    assert result.pages[0].page_id == "page-1"
    assert result.pages[0].page_name == "Travel Page"
    assert result.pages[0].instagram_account_id == "ig-1"
    assert result.pages[0].instagram_username == "travel_creator"
    assert result.pages[0].instagram_media_count == 42
    assert result.pages[1].page_id == "page-2"
    assert result.pages[1].instagram_account_id is None
    assert result.publishing_endpoints_called is False
    assert "travel_creator" in rendered
    assert "secret-token" not in rendered
    assert "Publishing endpoints called: no" in rendered
    assert [method for method, _url, _params in requested] == ["GET", "GET", "GET", "GET"]
    assert all("/media" not in url and "/media_publish" not in url for _method, url, _params in requested)


def test_update_meta_graph_account_ids_env_file_replaces_only_non_secret_ids(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POST_RELAY_USER_ACCESS_TOKEN=keep-secret-token\n"
        "POST_RELAY_FACEBOOK_PAGE_ID=old-page\n"
        "POST_RELAY_INSTAGRAM_ACCOUNT_ID=old-ig\n"
    )

    cli_module.update_meta_graph_account_ids_env_file(env_file, page_id="new-page", instagram_account_id="new-ig")

    assert env_file.read_text() == (
        "POST_RELAY_USER_ACCESS_TOKEN=keep-secret-token\n"
        "POST_RELAY_FACEBOOK_PAGE_ID=new-page\n"
        "POST_RELAY_INSTAGRAM_ACCOUNT_ID=new-ig\n"
    )


def test_meta_discover_accounts_cli_dry_run_does_not_call_network_or_print_token(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POST_RELAY_USER_ACCESS_TOKEN=secret-token\n")

    result = runner.invoke(app, ["meta", "discover-accounts", "--env-file", str(env_file), "--dry-run"])

    assert result.exit_code == 0
    assert "Meta Graph account discovery (dry run)" in result.output
    assert "https://graph.facebook.com/v19.0/me/accounts" in result.output
    assert "No network calls were made." in result.output
    assert "secret-token" not in result.output


def test_meta_discover_accounts_cli_can_update_non_secret_ids_after_execute(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("POST_RELAY_USER_ACCESS_TOKEN=secret-token\n")

    class FakeClient:
        def __init__(self, config):
            assert config.access_token == "secret-token"

        def discover_accounts(self):
            return cli_module.AccountDiscoveryResult(
                pages=[
                    cli_module.DiscoveredMetaAccount(
                        page_id="page-1",
                        page_name="Travel Page",
                        instagram_account_id="ig-1",
                        instagram_username="travel_creator",
                        instagram_media_count=42,
                    )
                ]
            )

        def discovery_dry_run_urls(self):
            raise AssertionError("dry run URLs should not be used in execute mode")

    monkeypatch.setattr(cli_module, "MetaGraphClient", FakeClient)

    result = runner.invoke(
        app,
        [
            "meta",
            "discover-accounts",
            "--env-file",
            str(env_file),
            "--execute",
            "--update-env",
            "--page-id",
            "page-1",
            "--instagram-account-id",
            "ig-1",
        ],
    )

    assert result.exit_code == 0
    assert "Meta Graph account discovery" in result.output
    assert "Travel Page" in result.output
    assert "Env file updated: yes" in result.output
    assert "secret-token" not in result.output
    assert "POST_RELAY_FACEBOOK_PAGE_ID=page-1" in env_file.read_text()
    assert "POST_RELAY_INSTAGRAM_ACCOUNT_ID=ig-1" in env_file.read_text()


def test_meta_oauth_authorization_url_uses_app_id_redirect_scope_and_state_without_secret():
    config = cli_module.load_meta_oauth_config(env_file=None, app_id="app-id-123", app_secret="app-secret-456")

    url = cli_module.build_meta_oauth_authorization_url(
        config,
        redirect_uri="http://localhost:8765/callback",
        state="local-state-123",
        scopes=["pages_show_list", "instagram_basic"],
    )

    assert url.startswith("https://www.facebook.com/v19.0/dialog/oauth?")
    assert "client_id=app-id-123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback" in url
    assert "state=local-state-123" in url
    assert "scope=pages_show_list%2Cinstagram_basic" in url
    assert "app-secret-456" not in url


def test_meta_graph_client_exchanges_oauth_code_without_publishing_or_leaking_secrets():
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        return {"access_token": "short-lived-user-token", "token_type": "bearer", "expires_in": 3600}

    client = MetaGraphClient(
        MetaGraphConfig(access_token="placeholder", app_id="app-id-123", app_secret="app-secret-456"),
        transport=fake_transport,
    )

    result = client.exchange_oauth_authorization_code(
        code="oauth-code-789",
        redirect_uri="http://localhost:8765/callback",
        now=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert result.access_token == "short-lived-user-token"
    assert result.expires_at.isoformat() == "2026-05-20T13:00:00+00:00"
    assert requested == [
        (
            "GET",
            "https://graph.facebook.com/v19.0/oauth/access_token",
            {
                "client_id": "app-id-123",
                "client_secret": "app-secret-456",
                "redirect_uri": "http://localhost:8765/callback",
                "code": "oauth-code-789",
            },
        )
    ]
    rendered = result.to_text(env_updated=False)
    assert "short-lived-user-token" not in rendered
    assert "Publishing endpoints called: no" in rendered
    assert all("/media" not in url and "/media_publish" not in url for _method, url, _params in requested)


def test_meta_oauth_login_cli_dry_run_prints_login_url_without_network_or_secrets(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POST_RELAY_META_APP_ID=app-id-123\n"
        "POST_RELAY_META_APP_SECRET=app-secret-456\n"
    )

    result = runner.invoke(
        app,
        ["meta", "oauth-login", "--env-file", str(env_file), "--state", "state-123"],
    )

    assert result.exit_code == 0
    assert "Meta OAuth login (dry run)" in result.output
    assert "https://www.facebook.com/v19.0/dialog/oauth" in result.output
    assert "app-id-123" in result.output
    assert "app-secret-456" not in result.output
    assert "No network calls were made." in result.output
    assert "No env file was changed." in result.output
    assert "Publishing endpoints called: no" in result.output


def test_meta_oauth_login_cli_execute_updates_token_and_non_secret_ids(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POST_RELAY_META_APP_ID=app-id-123\n"
        "POST_RELAY_META_APP_SECRET=app-secret-456\n"
        "POST_RELAY_USER_ACCESS_TOKEN=old-token\n"
    )

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def exchange_oauth_authorization_code(self, *, code, redirect_uri):
            assert code == "oauth-code-789"
            assert redirect_uri == "http://localhost:8765/callback"
            return cli_module.TokenExtensionResult(
                access_token="new-user-token",
                token_type="bearer",
                expires_in=3600,
                expires_at=datetime(2026, 5, 20, 13, 0, 0, tzinfo=timezone.utc),
            )

        def discover_accounts(self):
            assert self.config.access_token == "new-user-token"
            return cli_module.AccountDiscoveryResult(
                pages=[
                    cli_module.DiscoveredMetaAccount(
                        page_id="page-1",
                        page_name="Travel Page",
                        instagram_account_id="ig-1",
                        instagram_username="travel_creator",
                        instagram_media_count=42,
                    )
                ]
            )

    monkeypatch.setattr(cli_module, "MetaGraphClient", FakeClient)

    result = runner.invoke(
        app,
        [
            "meta",
            "oauth-login",
            "--env-file",
            str(env_file),
            "--execute",
            "--code",
            "oauth-code-789",
            "--update-env",
            "--page-id",
            "page-1",
            "--instagram-account-id",
            "ig-1",
        ],
    )

    assert result.exit_code == 0
    assert "Meta OAuth login completed" in result.output
    assert "Travel Page" in result.output
    assert "Env file updated: yes" in result.output
    assert "new-user-token" not in result.output
    assert "app-secret-456" not in result.output
    env_text = env_file.read_text()
    assert "POST_RELAY_USER_ACCESS_TOKEN=new-user-token" in env_text
    assert "POST_RELAY_FACEBOOK_PAGE_ID=page-1" in env_text
    assert "POST_RELAY_INSTAGRAM_ACCOUNT_ID=ig-1" in env_text
