from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from aws_utils.s3 import utils as s3_utils


class DummyClient:
    def __init__(self) -> None:
        self.download_calls: list[tuple[str, str, str, Any]] = []
        self.upload_calls: list[tuple[str, str, str, Any]] = []
        self.head_calls: list[tuple[str, str]] = []

    def download_file(
        self, bucket: str, key: str, destination: str, Config: Any
    ) -> None:  # noqa: N803
        self.download_calls.append((bucket, key, destination, Config))

    def upload_file(
        self, source: str, bucket: str, key: str, Config: Any
    ) -> None:  # noqa: N803
        self.upload_calls.append((source, bucket, key, Config))

    def head_object(
        self, *, Bucket: str, Key: str
    ) -> dict[str, Any]:  # noqa: N803
        self.head_calls.append((Bucket, Key))
        return {'Bucket': Bucket, 'Key': Key}


def make_client_error(code: str) -> ClientError:
    return ClientError(
        error_response={'Error': {'Code': code, 'Message': 'boom'}},
        operation_name='test',
    )


def test_download_file_success_creates_missing_directory(
    tmp_path: Path,
) -> None:
    client = DummyClient()
    destination = tmp_path / 'nested/dir/file.txt'

    result = s3_utils.download_file_from_s3(
        'bucket', 'key', destination, client=client, max_attempts=1
    )

    assert result == destination
    assert destination.parent.exists()
    assert client.download_calls[0][2] == str(destination)


def test_download_file_convert_no_such_key(tmp_path: Path) -> None:
    client = DummyClient()
    client.download_file = Mock(side_effect=make_client_error('NoSuchKey'))

    with pytest.raises(s3_utils.S3FileNotFoundError):
        s3_utils.download_file_from_s3(
            'bucket',
            'missing',
            tmp_path / 'file',
            client=client,
            max_attempts=1,
        )


def test_upload_file_requires_existing_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        s3_utils.upload_file_to_s3(
            tmp_path / 'missing', 'bucket', 'key', client=DummyClient()
        )


def test_upload_file_convert_access_denied(tmp_path: Path) -> None:
    source = tmp_path / 'data.txt'
    source.write_text('payload')
    client = DummyClient()
    client.upload_file = Mock(side_effect=make_client_error('AccessDenied'))

    with pytest.raises(s3_utils.S3AccessDeniedError):
        s3_utils.upload_file_to_s3(source, 'bucket', 'key', client=client)


class HeadErrorClient(DummyClient):
    def head_object(
        self, *, Bucket: str, Key: str
    ) -> dict[str, Any]:  # noqa: N803
        raise make_client_error('Boom')


def test_get_object_metadata_returns_none_on_error() -> None:
    client = HeadErrorClient()

    assert s3_utils.get_object_metadata('bucket', 'key', client=client) is None
