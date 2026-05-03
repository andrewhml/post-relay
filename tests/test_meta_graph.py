import pytest

from post_relay.meta_graph import (
    MetaGraphClient,
    MetaGraphConfig,
    MetaGraphConfigError,
    MetaGraphRequestError,
    ReadOnlyValidationResult,
    load_meta_graph_config,
    redact_secrets,
)


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
    assert "env-file-token" not in config.safe_summary()
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
