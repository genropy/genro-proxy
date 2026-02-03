# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Cloud storage fixtures for testing with Docker emulators.

Requires Docker containers running:
    docker compose up -d minio azurite gcs

Connections:
    MinIO (S3): http://localhost:9000 (access: minioadmin, secret: minioadmin)
    Azurite (Azure): http://localhost:10000 (account: devstoreaccount1)
    GCS Fake: http://localhost:4443
"""

from __future__ import annotations

import os
import socket

import pytest

from genro_proxy.storage import StorageManager


def pytest_configure(config):
    """Register cloud markers."""
    config.addinivalue_line("markers", "s3: marks tests requiring MinIO/S3")
    config.addinivalue_line("markers", "azure: marks tests requiring Azurite/Azure")
    config.addinivalue_line("markers", "gcs: marks tests requiring fake-gcs-server")


def _is_port_open(host: str, port: int) -> bool:
    """Check if a port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _is_s3fs_available() -> bool:
    """Check if s3fs is installed."""
    try:
        import s3fs  # noqa: F401
        return True
    except ImportError:
        return False


def _is_gcsfs_available() -> bool:
    """Check if gcsfs is installed."""
    try:
        import gcsfs  # noqa: F401
        return True
    except ImportError:
        return False


def _is_adlfs_available() -> bool:
    """Check if adlfs is installed."""
    try:
        import adlfs  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture(autouse=True)
def skip_if_cloud_unavailable(request):
    """Auto-skip cloud tests if services are not available."""
    if request.node.get_closest_marker("s3"):
        if not _is_port_open("localhost", 9000):
            pytest.skip("MinIO not available at localhost:9000")
        if not _is_s3fs_available():
            pytest.skip("s3fs not installed")

    if request.node.get_closest_marker("azure"):
        if not _is_port_open("localhost", 10000):
            pytest.skip("Azurite not available at localhost:10000")
        if not _is_adlfs_available():
            pytest.skip("adlfs not installed")

    if request.node.get_closest_marker("gcs"):
        if not _is_port_open("localhost", 4443):
            pytest.skip("fake-gcs-server not available at localhost:4443")
        if not _is_gcsfs_available():
            pytest.skip("gcsfs not installed")


@pytest.fixture
def s3_storage() -> StorageManager:
    """Create storage with MinIO S3 mount."""
    # Set environment for s3fs to connect to MinIO
    os.environ["AWS_ACCESS_KEY_ID"] = "minioadmin"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "minioadmin"

    s = StorageManager()
    s.configure([{
        "name": "s3data",
        "protocol": "s3",
        "bucket": "test-bucket",
        "endpoint_url": "http://localhost:9000",
    }])
    return s


@pytest.fixture
def azure_storage() -> StorageManager:
    """Create storage with Azurite Azure mount."""
    # Azurite default connection string
    conn_str = (
        "DefaultEndpointsProtocol=http;"
        "AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
        "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    )
    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = conn_str

    s = StorageManager()
    s.configure([{
        "name": "azuredata",
        "protocol": "azure",
        "container": "test-container",
        "account_name": "devstoreaccount1",
        "connection_string": conn_str,
    }])
    return s


@pytest.fixture
def gcs_storage() -> StorageManager:
    """Create storage with fake-gcs-server mount."""
    # Set environment for gcsfs to connect to fake GCS
    os.environ["STORAGE_EMULATOR_HOST"] = "http://localhost:4443"

    s = StorageManager()
    s.configure([{
        "name": "gcsdata",
        "protocol": "gcs",
        "bucket": "test-bucket",
        "endpoint_url": "http://localhost:4443",
    }])
    return s
