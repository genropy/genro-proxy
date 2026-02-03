# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Integration tests for cloud storage with Docker emulators.

Requires Docker containers running:
    docker compose up -d minio azurite gcs

And cloud dependencies installed:
    pip install genro-proxy[cloud]
"""

import pytest


@pytest.mark.s3
class TestS3Storage:
    """Tests for S3/MinIO storage operations."""

    async def test_write_and_read_bytes(self, s3_storage):
        """Write bytes to S3 and read back."""
        node = s3_storage.node("s3data:test/hello.txt")

        await node.write_bytes(b"Hello from MinIO!")
        content = await node.read_bytes()

        assert content == b"Hello from MinIO!"

    async def test_write_and_read_text(self, s3_storage):
        """Write text to S3 and read back."""
        node = s3_storage.node("s3data:test/greeting.txt")

        await node.write_text("Ciao da MinIO!")
        content = await node.read_text()

        assert content == "Ciao da MinIO!"

    async def test_exists(self, s3_storage):
        """Check file existence on S3."""
        import uuid
        unique_name = f"test/exists_{uuid.uuid4().hex}.txt"
        node = s3_storage.node(f"s3data:{unique_name}")

        # File doesn't exist yet
        assert not await node.exists()

        # Write and check again
        await node.write_bytes(b"data")
        assert await node.exists()

        # Cleanup
        await node.delete()

    async def test_delete(self, s3_storage):
        """Delete file from S3."""
        node = s3_storage.node("s3data:test/to_delete.txt")

        await node.write_bytes(b"delete me")
        assert await node.exists()

        await node.delete()
        assert not await node.exists()



@pytest.mark.azure
@pytest.mark.skip(reason="Requires manual container creation: az storage container create --name test-container")
class TestAzureStorage:
    """Tests for Azure/Azurite storage operations."""

    async def test_write_and_read_bytes(self, azure_storage):
        """Write bytes to Azure and read back."""
        node = azure_storage.node("azuredata:test/hello.txt")

        await node.write_bytes(b"Hello from Azurite!")
        content = await node.read_bytes()

        assert content == b"Hello from Azurite!"

    async def test_write_and_read_text(self, azure_storage):
        """Write text to Azure and read back."""
        node = azure_storage.node("azuredata:test/greeting.txt")

        await node.write_text("Ciao da Azurite!")
        content = await node.read_text()

        assert content == "Ciao da Azurite!"

    async def test_exists(self, azure_storage):
        """Check file existence on Azure."""
        node = azure_storage.node("azuredata:test/exists_test.txt")

        assert not await node.exists()
        await node.write_bytes(b"data")
        assert await node.exists()

    async def test_delete(self, azure_storage):
        """Delete file from Azure."""
        node = azure_storage.node("azuredata:test/to_delete.txt")

        await node.write_bytes(b"delete me")
        assert await node.exists()

        await node.delete()
        assert not await node.exists()


@pytest.mark.gcs
@pytest.mark.skip(reason="Requires manual bucket creation via fake-gcs-server API")
class TestGCSStorage:
    """Tests for GCS/fake-gcs-server storage operations."""

    async def test_write_and_read_bytes(self, gcs_storage):
        """Write bytes to GCS and read back."""
        node = gcs_storage.node("gcsdata:test/hello.txt")

        await node.write_bytes(b"Hello from fake-GCS!")
        content = await node.read_bytes()

        assert content == b"Hello from fake-GCS!"

    async def test_write_and_read_text(self, gcs_storage):
        """Write text to GCS and read back."""
        node = gcs_storage.node("gcsdata:test/greeting.txt")

        await node.write_text("Ciao da fake-GCS!")
        content = await node.read_text()

        assert content == "Ciao da fake-GCS!"

    async def test_exists(self, gcs_storage):
        """Check file existence on GCS."""
        node = gcs_storage.node("gcsdata:test/exists_test.txt")

        assert not await node.exists()
        await node.write_bytes(b"data")
        assert await node.exists()

    async def test_delete(self, gcs_storage):
        """Delete file from GCS."""
        node = gcs_storage.node("gcsdata:test/to_delete.txt")

        await node.write_bytes(b"delete me")
        assert await node.exists()

        await node.delete()
        assert not await node.exists()
