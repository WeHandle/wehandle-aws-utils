"""High level helpers around boto3's S3 client.

The goal of this module is to centralize the resilient download/upload logic that is
duplicated across different automation services.  The helpers wrap boto3 with sensible
defaults (timeouts, retries, multipart config) and convert common failure cases into
domain specific exceptions so that the caller can decide when an operation is retryable.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

__all__ = [
    'S3Error',
    'S3AccessDeniedError',
    'S3DownloadError',
    'S3FileNotFoundError',
    'S3UploadError',
    'S3Config',
    'TransferSettings',
    'get_s3_client',
    'download_file_from_s3',
    'upload_file_to_s3',
    'get_object_metadata',
]


class S3Error(Exception):
    """Base exception for S3 helpers."""


class S3FileNotFoundError(S3Error):
    """Raised when an object is missing from the bucket."""


class S3AccessDeniedError(S3Error):
    """Raised when AWS denies access to the requested object/bucket."""


class S3DownloadError(S3Error):
    """Raised when a download fails after exhausting the retry policy."""


class S3UploadError(S3Error):
    """Raised when an upload cannot be completed."""


@dataclass(frozen=True)
class S3Config:
    """Settings for creating boto3 S3 clients."""

    max_attempts: int = 10
    connect_timeout: int = 10
    read_timeout: int = 120
    tcp_keepalive: bool = True
    max_pool_connections: int = 50

    def to_botocore_config(self) -> Config:
        return Config(
            retries={'max_attempts': self.max_attempts, 'mode': 'standard'},
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            tcp_keepalive=self.tcp_keepalive,
            max_pool_connections=self.max_pool_connections,
        )


@dataclass(frozen=True)
class TransferSettings:
    """Tuning knobs for multipart transfers."""

    multipart_threshold: int = 8 * 1024 * 1024
    multipart_chunksize: int = 8 * 1024 * 1024
    max_concurrency: int = 8
    use_threads: bool = True

    def to_transfer_config(self) -> TransferConfig:
        return TransferConfig(
            multipart_threshold=self.multipart_threshold,
            multipart_chunksize=self.multipart_chunksize,
            max_concurrency=self.max_concurrency,
            use_threads=self.use_threads,
        )


_LOGGER = logging.getLogger('automation_aws_utils.s3')
_DEFAULT_BOTO_CONFIG = S3Config().to_botocore_config()
_DEFAULT_TRANSFER_CONFIG = TransferSettings().to_transfer_config()


def get_s3_client(*, config: Config | None = None) -> BaseClient:
    """Return a boto3 client already configured with sensible defaults."""
    return boto3.client('s3', config=config or _DEFAULT_BOTO_CONFIG)


def download_file_from_s3(
    bucket_name: str,
    s3_key: str,
    destination: str | Path,
    *,
    client: BaseClient | None = None,
    transfer_config: TransferConfig | None = None,
    max_attempts: int = 5,
    base_sleep_seconds: float = 1.0,
) -> Path:
    """Download an object from S3 to ``destination`` using exponential backoff."""
    if max_attempts < 1:
        raise ValueError('max_attempts must be greater than 0')
    if base_sleep_seconds <= 0:
        raise ValueError('base_sleep_seconds must be greater than 0')

    client = client or get_s3_client()
    transfer_config = transfer_config or _DEFAULT_TRANSFER_CONFIG

    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    attempt = 0
    while attempt < max_attempts:
        try:
            _LOGGER.info(
                'Downloading s3://%s/%s to %s (attempt %d/%d)',
                bucket_name,
                s3_key,
                destination_path,
                attempt + 1,
                max_attempts,
            )
            start = time.time()
            client.download_file(
                bucket_name,
                s3_key,
                str(destination_path),
                Config=transfer_config,
            )
            _LOGGER.info(
                'Download completed in %.2fs for s3://%s/%s',
                time.time() - start,
                bucket_name,
                s3_key,
            )
            return destination_path

        except (
            ConnectTimeoutError,
            ReadTimeoutError,
            EndpointConnectionError,
        ) as exc:
            attempt += 1
            if attempt >= max_attempts:
                raise S3DownloadError(
                    f'Download failed after {max_attempts} attempts due to connection errors'
                ) from exc
            delay = min(base_sleep_seconds * (2 ** (attempt - 1)), 30.0)
            _LOGGER.warning(
                'Transient S3 error (%s). Retrying in %.1fs (%d/%d)...',
                exc.__class__.__name__,
                delay,
                attempt,
                max_attempts,
            )
            time.sleep(delay)
            continue
        except ClientError as exc:  # pragma: no cover - mapped paths tested
            code = _extract_error_code(exc)
            if code == 'NoSuchKey':
                raise S3FileNotFoundError(
                    f's3://{bucket_name}/{s3_key} not found'
                ) from exc
            if code == 'AccessDenied':
                raise S3AccessDeniedError(
                    f'Access denied for s3://{bucket_name}/{s3_key}'
                ) from exc
            attempt += 1
            if attempt >= max_attempts:
                raise S3DownloadError(
                    f'Download failed after {max_attempts} attempts (last error: {code or exc})'
                ) from exc
            delay = min(base_sleep_seconds * (2 ** (attempt - 1)), 30.0)
            _LOGGER.warning(
                'ClientError %s while downloading %s. Retrying in %.1fs (%d/%d)...',
                code,
                s3_key,
                delay,
                attempt,
                max_attempts,
            )
            time.sleep(delay)
        except Exception as exc:  # pragma: no cover - defensive
            attempt += 1
            if attempt >= max_attempts:
                raise S3DownloadError(
                    f'Download failed after {max_attempts} attempts'
                ) from exc
            delay = min(base_sleep_seconds * (2 ** (attempt - 1)), 30.0)
            _LOGGER.warning(
                'Unexpected error while downloading %s (%s). Retrying in %.1fs...',
                s3_key,
                exc,
                delay,
            )
            time.sleep(delay)

    raise S3DownloadError(f'Download failed after {max_attempts} attempts')


def upload_file_to_s3(
    source: str | Path,
    bucket_name: str,
    s3_key: str,
    *,
    client: BaseClient | None = None,
    transfer_config: TransferConfig | None = None,
) -> None:
    """Upload ``source`` to ``bucket_name`` using multipart transfers by default."""
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(f'Local file not found: {source_path}')

    client = client or get_s3_client()
    transfer_config = transfer_config or _DEFAULT_TRANSFER_CONFIG

    _LOGGER.info(
        'Uploading %s to s3://%s/%s', source_path, bucket_name, s3_key
    )
    try:
        client.upload_file(
            str(source_path), bucket_name, s3_key, Config=transfer_config
        )
    except ClientError as exc:
        code = _extract_error_code(exc)
        if code == 'AccessDenied':
            message = (
                f'Access denied while uploading to s3://{bucket_name}/{s3_key}'
            )
            raise S3AccessDeniedError(message) from exc
        message = (
            f'Failed to upload to s3://{bucket_name}/{s3_key}: {code or exc}'
        )
        raise S3UploadError(message) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise S3UploadError(
            f'Failed to upload to s3://{bucket_name}/{s3_key}'
        ) from exc


def get_object_metadata(
    bucket_name: str,
    s3_key: str,
    *,
    client: BaseClient | None = None,
) -> Mapping[str, Any] | None:
    """Return the metadata from ``HeadObject`` without downloading the entire file."""
    client = client or get_s3_client()
    try:
        return client.head_object(Bucket=bucket_name, Key=s3_key)
    except ClientError as exc:
        _LOGGER.warning(
            'Unable to fetch metadata for s3://%s/%s (error: %s)',
            bucket_name,
            s3_key,
            _extract_error_code(exc) or exc,
        )
        return None
    except Exception:  # pragma: no cover - defensive
        _LOGGER.exception(
            'Unexpected error while fetching metadata for s3://%s/%s',
            bucket_name,
            s3_key,
        )
        return None


def _extract_error_code(exc: ClientError) -> str | None:
    error = getattr(exc, 'response', {}).get('Error', {})
    code = error.get('Code')
    if isinstance(code, str):
        return code
    return None
