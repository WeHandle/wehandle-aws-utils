from __future__ import annotations

import base64
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from automation_aws_utils import secrets_manager


def make_client_error(code: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "kaboom"}},
        operation_name="GetSecretValue",
    )


class StubSecretsManagerClient:
    def __init__(
        self,
        *,
        secret_string: str | None = None,
        secret_binary: bytes | None = None,
        error: ClientError | None = None,
    ) -> None:
        self.secret_string = secret_string
        self.secret_binary = secret_binary
        self.error = error
        self.requests: list[dict[str, str]] = []

    def get_secret_value(self, **kwargs: str) -> dict[str, object]:  # noqa: D401
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        response: dict[str, object] = {}
        if self.secret_string is not None:
            response["SecretString"] = self.secret_string
        if self.secret_binary is not None:
            response["SecretBinary"] = self.secret_binary
        return response


def test_fetch_secret_value_returns_string() -> None:
    client = StubSecretsManagerClient(secret_string="payload")

    value = secrets_manager.fetch_secret_value(
        "my-secret", client=client, version_stage="AWSCURRENT"
    )

    assert value == "payload"
    assert client.requests[0]["SecretId"] == "my-secret"
    assert client.requests[0]["VersionStage"] == "AWSCURRENT"


def test_fetch_secret_value_decodes_binary() -> None:
    encoded = base64.b64encode(b"binary-data")
    client = StubSecretsManagerClient(secret_binary=encoded)

    assert secrets_manager.fetch_secret_value("my-secret", client=client) == b"binary-data"


def test_fetch_secret_json_returns_dict() -> None:
    client = StubSecretsManagerClient(secret_string='{"foo": "bar"}')

    value = secrets_manager.fetch_secret_json("json-secret", client=client)

    assert value == {"foo": "bar"}


def test_write_secret_to_file(tmp_path: Path) -> None:
    client = StubSecretsManagerClient(secret_string="credentials")

    output = tmp_path / "config/google.json"
    secrets_manager.write_secret_to_file("creds", output, client=client)

    assert output.read_text() == "credentials"


def test_fetch_secret_value_raises_for_missing_secret() -> None:
    client = StubSecretsManagerClient(error=make_client_error("ResourceNotFoundException"))

    with pytest.raises(secrets_manager.SecretNotFoundError):
        secrets_manager.fetch_secret_value("missing", client=client)

