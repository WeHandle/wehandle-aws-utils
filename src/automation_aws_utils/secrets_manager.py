"""Utilities for interacting with AWS Secrets Manager.

These helpers encapsulate the repetitive logic found in our services: fetching
secrets (as raw strings, JSON or binary payloads), handling common failures and
persisting credentials to disk for third-party SDKs such as Google Vertex AI.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

__all__ = [
    "SecretsManagerError",
    "SecretNotFoundError",
    "SecretAccessDeniedError",
    "SecretDecryptionError",
    "SecretRetrievalError",
    "SecretsManagerConfig",
    "get_secrets_manager_client",
    "fetch_secret_value",
    "fetch_secret_json",
    "write_secret_to_file",
]


class SecretsManagerError(Exception):
    """Base exception raised by secrets helpers."""


class SecretNotFoundError(SecretsManagerError):
    """Raised when a secret cannot be found."""


class SecretAccessDeniedError(SecretsManagerError):
    """Raised when AWS denies access to a secret."""


class SecretDecryptionError(SecretsManagerError):
    """Raised when Secrets Manager cannot decrypt the payload."""


class SecretRetrievalError(SecretsManagerError):
    """Raised for other client-side failures."""


@dataclass(frozen=True)
class SecretsManagerConfig:
    """Configuration used to materialize boto3 Secrets Manager clients."""

    region_name: str | None = None
    profile_name: str | None = None

    def create_client(self) -> BaseClient:
        return _cached_client(self.region_name, self.profile_name)


def get_secrets_manager_client(
    *,
    region_name: str | None = None,
    profile_name: str | None = None,
) -> BaseClient:
    """Return a cached Secrets Manager client configured with the provided scope."""
    return _cached_client(region_name, profile_name)


@lru_cache(maxsize=8)
def _cached_client(region_name: str | None, profile_name: str | None) -> BaseClient:
    session_kwargs = {}
    if profile_name:
        session_kwargs["profile_name"] = profile_name
    session = boto3.session.Session(**session_kwargs)
    return session.client("secretsmanager", region_name=region_name)


def fetch_secret_value(
    secret_id: str,
    *,
    client: BaseClient | None = None,
    region_name: str | None = None,
    profile_name: str | None = None,
    version_stage: str | None = None,
) -> str | bytes:
    """Fetch the raw secret value as string or bytes."""
    if client is None:
        client = get_secrets_manager_client(region_name=region_name, profile_name=profile_name)

    request: dict[str, Any] = {"SecretId": secret_id}
    if version_stage:
        request["VersionStage"] = version_stage

    try:
        response = client.get_secret_value(**request)
    except ClientError as exc:  # pragma: no cover - error branches unit tested below
        _raise_from_client_error(secret_id, exc)

    if (secret_string := response.get("SecretString")) is not None:
        return secret_string

    secret_binary = response.get("SecretBinary")
    if secret_binary is not None:
        return base64.b64decode(secret_binary)

    raise SecretRetrievalError(
        f"Secret {secret_id} does not contain SecretString nor SecretBinary data"
    )


def fetch_secret_json(
    secret_id: str,
    *,
    client: BaseClient | None = None,
    region_name: str | None = None,
    profile_name: str | None = None,
    version_stage: str | None = None,
) -> dict[str, Any]:
    """Fetch and JSON-decode a secret, returning a Python dict."""
    import json

    value = fetch_secret_value(
        secret_id,
        client=client,
        region_name=region_name,
        profile_name=profile_name,
        version_stage=version_stage,
    )
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        decoded: dict[str, Any] = json.loads(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - deterministic
        raise SecretRetrievalError(f"Secret {secret_id} does not contain valid JSON") from exc
    if not isinstance(decoded, dict):
        raise SecretRetrievalError(f"Secret {secret_id} JSON payload is not an object")
    return decoded


def write_secret_to_file(
    secret_id: str,
    destination: str | Path,
    *,
    client: BaseClient | None = None,
    region_name: str | None = None,
    profile_name: str | None = None,
    version_stage: str | None = None,
    encoding: str = "utf-8",
    file_permissions: int | None = 0o600,
) -> Path:
    """Persist the secret payload to ``destination`` and optionally tighten permissions."""
    secret_value = fetch_secret_value(
        secret_id,
        client=client,
        region_name=region_name,
        profile_name=profile_name,
        version_stage=version_stage,
    )

    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(secret_value, bytes):
        destination_path.write_bytes(secret_value)
    else:
        destination_path.write_text(secret_value, encoding=encoding)

    if file_permissions is not None:
        os.chmod(destination_path, file_permissions)

    return destination_path


def _raise_from_client_error(secret_id: str, exc: ClientError) -> None:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    message = f"Unable to fetch secret {secret_id}: {code or exc}"

    if code == "ResourceNotFoundException":
        raise SecretNotFoundError(f"Secret {secret_id} was not found") from exc
    if code in {"AccessDeniedException", "AccessDenied"}:
        raise SecretAccessDeniedError(message) from exc
    if code == "DecryptionFailureException":
        raise SecretDecryptionError(message) from exc
    raise SecretRetrievalError(message) from exc

