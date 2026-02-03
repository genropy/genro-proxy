# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for StorageNode."""

import time

import pytest

from proxy.storage.manager import StorageManager
from proxy.storage.node import StorageError, StorageNode


@pytest.fixture
def storage_manager(tmp_path):
    """Create a StorageManager with local mount."""
    manager = StorageManager()
    manager.register("HOME", {
        "protocol": "local",
        "base_path": str(tmp_path / "storage"),
        "public_base_url": "http://example.com/files",
        "secret_key": "test-secret-key",
    })
    return manager


@pytest.fixture
def storage_node(storage_manager) -> StorageNode:
    """Create a StorageNode for testing."""
    return storage_manager.node("HOME:test/file.txt")


class TestProperties:
    """Tests for StorageNode properties."""

    def test_basename(self, storage_node):
        """basename returns filename with extension."""
        assert storage_node.basename == "file.txt"

    def test_stem(self, storage_node):
        """stem returns filename without extension."""
        assert storage_node.stem == "file"

    def test_suffix(self, storage_node):
        """suffix returns file extension with dot."""
        assert storage_node.suffix == ".txt"

    def test_fullpath(self, storage_node):
        """fullpath returns mount:path."""
        assert storage_node.fullpath == "HOME:test/file.txt"

    def test_path(self, storage_node):
        """path returns path without mount prefix."""
        assert storage_node.path == "test/file.txt"

    def test_mount_name(self, storage_node):
        """mount_name returns mount name."""
        assert storage_node.mount_name == "HOME"

    def test_parent(self, storage_node):
        """parent returns parent directory node."""
        parent = storage_node.parent
        assert parent.path == "test"
        assert parent.mount_name == "HOME"

    def test_parent_of_root(self, storage_manager):
        """parent of root returns empty path."""
        node = storage_manager.node("HOME:")
        parent = node.parent
        assert parent.path == ""

    def test_mimetype_txt(self, storage_node):
        """mimetype returns text/plain for .txt."""
        assert storage_node.mimetype == "text/plain"

    def test_mimetype_unknown(self, storage_manager):
        """mimetype returns application/octet-stream for unknown."""
        node = storage_manager.node("HOME:file.xyz123")
        assert node.mimetype == "application/octet-stream"


class TestChild:
    """Tests for StorageNode.child() method."""

    def test_child_single_part(self, storage_manager):
        """child() with single part."""
        node = storage_manager.node("HOME:test")
        child = node.child("file.txt")
        assert child.path == "test/file.txt"

    def test_child_multiple_parts(self, storage_manager):
        """child() with multiple parts."""
        node = storage_manager.node("HOME:data")
        child = node.child("sub", "dir", "file.txt")
        assert child.path == "data/sub/dir/file.txt"

    def test_child_from_root(self, storage_manager):
        """child() from root creates proper path."""
        node = storage_manager.node("HOME:")
        child = node.child("test", "file.txt")
        assert child.path == "test/file.txt"


class TestLocalIOExists:
    """Tests for StorageNode local I/O - exists()."""

    async def test_exists_false(self, storage_node):
        """exists() returns False when file doesn't exist."""
        assert await storage_node.exists() is False

    async def test_exists_true(self, storage_node, tmp_path):
        """exists() returns True when file exists."""
        file_path = tmp_path / "storage" / "test" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("content")
        assert await storage_node.exists() is True


class TestLocalIOIsFile:
    """Tests for StorageNode local I/O - is_file()."""

    async def test_is_file_true(self, storage_node, tmp_path):
        """is_file() returns True for file."""
        file_path = tmp_path / "storage" / "test" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("content")
        assert await storage_node.is_file() is True

    async def test_is_file_false_dir(self, storage_manager, tmp_path):
        """is_file() returns False for directory."""
        dir_path = tmp_path / "storage" / "testdir"
        dir_path.mkdir(parents=True)
        node = storage_manager.node("HOME:testdir")
        assert await node.is_file() is False


class TestLocalIOIsDir:
    """Tests for StorageNode local I/O - is_dir()."""

    async def test_is_dir_true(self, storage_manager, tmp_path):
        """is_dir() returns True for directory."""
        dir_path = tmp_path / "storage" / "testdir"
        dir_path.mkdir(parents=True)
        node = storage_manager.node("HOME:testdir")
        assert await node.is_dir() is True

    async def test_is_dir_false_file(self, storage_node, tmp_path):
        """is_dir() returns False for file."""
        file_path = tmp_path / "storage" / "test" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("content")
        assert await storage_node.is_dir() is False


class TestLocalIOSize:
    """Tests for StorageNode local I/O - size()."""

    async def test_size(self, storage_node, tmp_path):
        """size() returns file size in bytes."""
        file_path = tmp_path / "storage" / "test" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"hello world")
        size = await storage_node.size()
        assert size == 11


class TestLocalIOMtime:
    """Tests for StorageNode local I/O - mtime()."""

    async def test_mtime(self, storage_node, tmp_path):
        """mtime() returns modification time."""
        file_path = tmp_path / "storage" / "test" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("content")
        mtime = await storage_node.mtime()
        assert mtime > 0
        assert mtime <= time.time()


class TestLocalIOReadWrite:
    """Tests for StorageNode local I/O - read/write."""

    async def test_write_and_read_bytes(self, storage_node):
        """write_bytes() and read_bytes() work correctly."""
        data = b"binary content \x00\xff"
        await storage_node.write_bytes(data)
        result = await storage_node.read_bytes()
        assert result == data

    async def test_write_and_read_text(self, storage_node):
        """write_text() and read_text() work correctly."""
        text = "Hello, World! 🌍"
        await storage_node.write_text(text)
        result = await storage_node.read_text()
        assert result == text

    async def test_write_creates_parent_dirs(self, storage_manager):
        """write_bytes() creates parent directories."""
        node = storage_manager.node("HOME:deep/nested/path/file.txt")
        await node.write_bytes(b"content")
        result = await node.read_bytes()
        assert result == b"content"


class TestLocalIODelete:
    """Tests for StorageNode local I/O - delete()."""

    async def test_delete_file(self, storage_node, tmp_path):
        """delete() removes file and returns True."""
        file_path = tmp_path / "storage" / "test" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("content")

        result = await storage_node.delete()

        assert result is True
        assert not file_path.exists()

    async def test_delete_directory(self, storage_manager, tmp_path):
        """delete() removes directory recursively."""
        dir_path = tmp_path / "storage" / "testdir"
        dir_path.mkdir(parents=True)
        (dir_path / "subfile.txt").write_text("content")

        node = storage_manager.node("HOME:testdir")
        result = await node.delete()

        assert result is True
        assert not dir_path.exists()

    async def test_delete_not_found(self, storage_node):
        """delete() returns False when file doesn't exist."""
        result = await storage_node.delete()
        assert result is False


class TestLocalIOMkdir:
    """Tests for StorageNode local I/O - mkdir()."""

    async def test_mkdir(self, storage_manager, tmp_path):
        """mkdir() creates directory."""
        # Create parent "storage" first
        (tmp_path / "storage").mkdir()
        node = storage_manager.node("HOME:newdir")
        await node.mkdir()
        assert (tmp_path / "storage" / "newdir").is_dir()

    async def test_mkdir_parents(self, storage_manager, tmp_path):
        """mkdir(parents=True) creates parent directories."""
        node = storage_manager.node("HOME:deep/nested/dir")
        await node.mkdir(parents=True)
        assert (tmp_path / "storage" / "deep" / "nested" / "dir").is_dir()

    async def test_mkdir_exist_ok(self, storage_manager, tmp_path):
        """mkdir(exist_ok=True) doesn't raise if exists."""
        dir_path = tmp_path / "storage" / "existing"
        dir_path.mkdir(parents=True)

        node = storage_manager.node("HOME:existing")
        await node.mkdir(exist_ok=True)  # Should not raise


class TestLocalIOChildren:
    """Tests for StorageNode local I/O - children()."""

    async def test_children_empty(self, storage_manager, tmp_path):
        """children() returns empty list for empty directory."""
        dir_path = tmp_path / "storage" / "emptydir"
        dir_path.mkdir(parents=True)

        node = storage_manager.node("HOME:emptydir")
        children = await node.children()
        assert children == []

    async def test_children_returns_nodes(self, storage_manager, tmp_path):
        """children() returns StorageNode list."""
        dir_path = tmp_path / "storage" / "parent"
        dir_path.mkdir(parents=True)
        (dir_path / "file1.txt").write_text("a")
        (dir_path / "file2.txt").write_text("b")
        (dir_path / "subdir").mkdir()

        node = storage_manager.node("HOME:parent")
        children = await node.children()

        assert len(children) == 3
        names = [c.basename for c in children]
        assert "file1.txt" in names
        assert "file2.txt" in names
        assert "subdir" in names

    async def test_children_sorted(self, storage_manager, tmp_path):
        """children() returns sorted by name."""
        dir_path = tmp_path / "storage" / "sorted"
        dir_path.mkdir(parents=True)
        (dir_path / "z.txt").write_text("")
        (dir_path / "a.txt").write_text("")
        (dir_path / "m.txt").write_text("")

        node = storage_manager.node("HOME:sorted")
        children = await node.children()

        names = [c.basename for c in children]
        assert names == ["a.txt", "m.txt", "z.txt"]

    async def test_children_not_dir(self, storage_node, tmp_path):
        """children() returns empty list for file."""
        file_path = tmp_path / "storage" / "test" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("content")

        children = await storage_node.children()
        assert children == []


class TestMd5Hash:
    """Tests for StorageNode.md5hash() method."""

    async def test_md5hash(self, storage_node):
        """md5hash() calculates correct MD5."""
        await storage_node.write_bytes(b"hello")
        hash_result = await storage_node.md5hash()
        # MD5 of "hello" is 5d41402abc4b2a76b9719d911017c592
        assert hash_result == "5d41402abc4b2a76b9719d911017c592"


class TestLocalSignedUrl:
    """Tests for StorageNode URL generation."""

    def test_url_generates_signed_url(self, storage_node):
        """url() generates signed URL with token."""
        url = storage_node.url(expires_in=3600)
        assert url.startswith("http://example.com/files/")
        assert "?token=" in url

    def test_url_without_public_base_url_raises(self, storage_manager, tmp_path):
        """url() raises StorageError if no public_base_url."""
        manager = StorageManager()
        manager.register("NOURL", {
            "protocol": "local",
            "base_path": str(tmp_path),
        })
        node = manager.node("NOURL:file.txt")

        with pytest.raises(StorageError, match="requires 'public_base_url'"):
            node.url()

    def test_verify_url_token_valid(self, storage_node):
        """verify_url_token() returns True for valid token."""
        url = storage_node.url(expires_in=3600)
        token = url.split("?token=")[1]
        assert storage_node.verify_url_token(token) is True

    def test_verify_url_token_expired(self, storage_node):
        """verify_url_token() returns False for expired token."""
        url = storage_node.url(expires_in=-10)  # Already expired
        token = url.split("?token=")[1]
        assert storage_node.verify_url_token(token) is False

    def test_verify_url_token_invalid_format(self, storage_node):
        """verify_url_token() returns False for invalid format."""
        assert storage_node.verify_url_token("invalid") is False
        assert storage_node.verify_url_token("") is False
        assert storage_node.verify_url_token("abc-def-ghi") is False

    def test_verify_url_token_wrong_signature(self, storage_node):
        """verify_url_token() returns False for wrong signature."""
        future_time = int(time.time()) + 3600
        fake_token = f"{future_time}-wrongsignature"
        assert storage_node.verify_url_token(fake_token) is False


class TestCloudPathGeneration:
    """Tests for cloud path generation."""

    def test_get_cloud_path_s3(self, tmp_path):
        """_get_cloud_path() for S3 returns bucket/prefix/path."""
        manager = StorageManager()
        manager.register("S3", {
            "protocol": "s3",
            "bucket": "my-bucket",
            "prefix": "data",
        })
        node = manager.node("S3:files/test.txt")
        assert node._get_cloud_path() == "my-bucket/data/files/test.txt"

    def test_get_cloud_path_s3_no_prefix(self, tmp_path):
        """_get_cloud_path() for S3 without prefix."""
        manager = StorageManager()
        manager.register("S3", {
            "protocol": "s3",
            "bucket": "my-bucket",
        })
        node = manager.node("S3:files/test.txt")
        assert node._get_cloud_path() == "my-bucket/files/test.txt"

    def test_get_cloud_path_gcs(self, tmp_path):
        """_get_cloud_path() for GCS returns bucket/prefix/path."""
        manager = StorageManager()
        manager.register("GCS", {
            "protocol": "gcs",
            "bucket": "my-gcs-bucket",
            "prefix": "archive",
        })
        node = manager.node("GCS:docs/report.pdf")
        assert node._get_cloud_path() == "my-gcs-bucket/archive/docs/report.pdf"

    def test_get_cloud_path_azure(self, tmp_path):
        """_get_cloud_path() for Azure returns container/prefix/path."""
        manager = StorageManager()
        manager.register("AZ", {
            "protocol": "azure",
            "container": "my-container",
            "prefix": "backup",
        })
        node = manager.node("AZ:files/data.json")
        assert node._get_cloud_path() == "my-container/backup/files/data.json"

    def test_get_cloud_path_azure_no_prefix(self, tmp_path):
        """_get_cloud_path() for Azure without prefix."""
        manager = StorageManager()
        manager.register("AZ", {
            "protocol": "azure",
            "container": "my-container",
        })
        node = manager.node("AZ:files/data.json")
        assert node._get_cloud_path() == "my-container/files/data.json"


class TestGetFs:
    """Tests for _get_fs() filesystem creation."""

    def test_get_fs_unsupported_protocol(self):
        """_get_fs() raises for unsupported protocol."""
        manager = StorageManager()
        manager.register("UNKNOWN", {
            "protocol": "ftp",  # Not supported
        })
        node = manager.node("UNKNOWN:file.txt")

        with pytest.raises(ValueError, match="Unsupported cloud protocol: ftp"):
            node._get_fs()

    def test_get_fs_returns_cached(self):
        """_get_fs() returns cached filesystem."""
        from unittest.mock import MagicMock

        manager = StorageManager()
        manager.register("CACHED", {"protocol": "s3", "bucket": "b"})
        node = manager.node("CACHED:test.txt")

        # Inject into cache
        mock_fs = MagicMock()
        node._fs_cache["CACHED"] = mock_fs

        # Should return cached
        result = node._get_fs()
        assert result is mock_fs

    def test_get_fs_no_fsspec(self, monkeypatch):
        """_get_fs() raises ImportError when fsspec not available."""
        import sys
        # Temporarily remove fsspec from modules
        original_modules = sys.modules.copy()

        def mock_import(name, *args, **kwargs):
            if name == "fsspec":
                raise ImportError("No module named 'fsspec'")
            return original_modules.get(name)

        manager = StorageManager()
        manager.register("S3", {"protocol": "s3", "bucket": "b"})
        node = manager.node("S3:test.txt")
        # Clear cache to force import
        node._fs_cache.clear()

        # Use monkeypatch to mock builtins.__import__
        monkeypatch.setattr("builtins.__import__", mock_import)

        with pytest.raises(ImportError, match="Cloud storage requires fsspec"):
            node._get_fs()

    def test_get_fs_creates_s3(self):
        """_get_fs() creates S3 filesystem with fsspec."""
        pytest.importorskip("fsspec")
        pytest.importorskip("s3fs")

        manager = StorageManager()
        manager.register("S3TEST", {
            "protocol": "s3",
            "bucket": "my-bucket",
            "aws_access_key_id": "test-key",
            "aws_secret_access_key": "test-secret",
        })
        node = manager.node("S3TEST:test.txt")
        node._fs_cache.clear()

        # This will create real S3 filesystem (won't connect without real creds)
        fs = node._get_fs()
        assert fs is not None
        # Verify it's cached
        assert "S3TEST" in node._fs_cache

    def test_get_fs_creates_gcs(self):
        """_get_fs() creates GCS filesystem with fsspec."""
        pytest.importorskip("fsspec")
        gcsfs = pytest.importorskip("gcsfs")

        manager = StorageManager()
        manager.register("GCSTEST", {
            "protocol": "gcs",
            "bucket": "my-bucket",
            "project": "my-project",
            "token": "anon",  # Use anonymous for testing
        })
        node = manager.node("GCSTEST:test.txt")
        node._fs_cache.clear()

        fs = node._get_fs()
        assert fs is not None
        assert "GCSTEST" in node._fs_cache

    def test_get_fs_creates_azure(self):
        """_get_fs() creates Azure filesystem with fsspec."""
        pytest.importorskip("fsspec")
        pytest.importorskip("adlfs")

        manager = StorageManager()
        manager.register("AZTEST", {
            "protocol": "azure",
            "container": "my-container",
            "account_name": "testaccount",
        })
        node = manager.node("AZTEST:test.txt")
        node._fs_cache.clear()

        fs = node._get_fs()
        assert fs is not None
        assert "AZTEST" in node._fs_cache


class TestCloudOperations:
    """Tests for cloud operations using mocked filesystem."""

    @pytest.fixture
    def mock_fs(self):
        """Create a mock fsspec filesystem."""
        from unittest.mock import MagicMock
        return MagicMock()

    @pytest.fixture
    def s3_node(self, mock_fs):
        """Create an S3 node with mocked filesystem."""
        manager = StorageManager()
        manager.register("S3", {
            "protocol": "s3",
            "bucket": "test-bucket",
            "prefix": "data",
        })
        node = manager.node("S3:files/test.txt")
        # Inject mocked fs into cache
        node._fs_cache["S3"] = mock_fs
        return node

    async def test_cloud_exists(self, s3_node, mock_fs):
        """_cloud_exists() calls fs.exists."""
        mock_fs.exists.return_value = True
        result = await s3_node.exists()
        assert result is True
        mock_fs.exists.assert_called_once_with("test-bucket/data/files/test.txt")

    async def test_cloud_is_file(self, s3_node, mock_fs):
        """_cloud_is_file() calls fs.isfile."""
        mock_fs.isfile.return_value = True
        result = await s3_node.is_file()
        assert result is True
        mock_fs.isfile.assert_called_once_with("test-bucket/data/files/test.txt")

    async def test_cloud_is_dir(self, s3_node, mock_fs):
        """_cloud_is_dir() calls fs.isdir."""
        mock_fs.isdir.return_value = True
        result = await s3_node.is_dir()
        assert result is True
        mock_fs.isdir.assert_called_once_with("test-bucket/data/files/test.txt")

    async def test_cloud_size(self, s3_node, mock_fs):
        """_cloud_size() calls fs.size."""
        mock_fs.size.return_value = 1234
        result = await s3_node.size()
        assert result == 1234
        mock_fs.size.assert_called_once_with("test-bucket/data/files/test.txt")

    async def test_cloud_size_none(self, s3_node, mock_fs):
        """_cloud_size() returns 0 when size is None."""
        mock_fs.size.return_value = None
        result = await s3_node.size()
        assert result == 0

    async def test_cloud_mtime_float(self, s3_node, mock_fs):
        """_cloud_mtime() returns float mtime."""
        mock_fs.info.return_value = {"mtime": 1234567890.5}
        result = await s3_node.mtime()
        assert result == 1234567890.5

    async def test_cloud_mtime_timestamp(self, s3_node, mock_fs):
        """_cloud_mtime() handles datetime with timestamp()."""
        from unittest.mock import MagicMock
        mock_dt = MagicMock()
        mock_dt.timestamp.return_value = 1234567890.0
        mock_fs.info.return_value = {"LastModified": mock_dt}
        result = await s3_node.mtime()
        assert result == 1234567890.0

    async def test_cloud_mtime_none(self, s3_node, mock_fs):
        """_cloud_mtime() returns 0.0 when no mtime."""
        mock_fs.info.return_value = {}
        result = await s3_node.mtime()
        assert result == 0.0

    async def test_cloud_read_bytes(self, s3_node, mock_fs):
        """_cloud_read_bytes() reads from fs."""
        from unittest.mock import MagicMock
        mock_file = MagicMock()
        mock_file.read.return_value = b"content"
        mock_fs.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_fs.open.return_value.__exit__ = MagicMock(return_value=None)

        result = await s3_node.read_bytes()
        assert result == b"content"

    async def test_cloud_read_bytes_string(self, s3_node, mock_fs):
        """_cloud_read_bytes() encodes string response."""
        from unittest.mock import MagicMock
        mock_file = MagicMock()
        mock_file.read.return_value = "text content"
        mock_fs.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_fs.open.return_value.__exit__ = MagicMock(return_value=None)

        result = await s3_node.read_bytes()
        assert result == b"text content"

    async def test_cloud_write_bytes(self, s3_node, mock_fs):
        """_cloud_write_bytes() writes to fs."""
        from unittest.mock import MagicMock
        mock_file = MagicMock()
        mock_fs.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_fs.open.return_value.__exit__ = MagicMock(return_value=None)

        await s3_node.write_bytes(b"new content")
        mock_file.write.assert_called_once_with(b"new content")

    async def test_cloud_delete_file(self, s3_node, mock_fs):
        """_cloud_delete() removes file."""
        mock_fs.exists.return_value = True
        mock_fs.isdir.return_value = False

        result = await s3_node.delete()

        assert result is True
        mock_fs.rm.assert_called_once_with("test-bucket/data/files/test.txt")

    async def test_cloud_delete_dir(self, s3_node, mock_fs):
        """_cloud_delete() removes directory recursively."""
        mock_fs.exists.return_value = True
        mock_fs.isdir.return_value = True

        result = await s3_node.delete()

        assert result is True
        mock_fs.rm.assert_called_once_with("test-bucket/data/files/test.txt", recursive=True)

    async def test_cloud_delete_not_found(self, s3_node, mock_fs):
        """_cloud_delete() returns False when not exists."""
        mock_fs.exists.return_value = False

        result = await s3_node.delete()
        assert result is False

    async def test_cloud_mkdir(self, s3_node, mock_fs):
        """_cloud_mkdir() calls makedirs."""
        await s3_node.mkdir(parents=True, exist_ok=True)
        mock_fs.makedirs.assert_called_once_with("test-bucket/data/files/test.txt", exist_ok=True)

    async def test_cloud_children(self, s3_node, mock_fs):
        """_cloud_children() returns StorageNode list."""
        mock_fs.isdir.return_value = True
        mock_fs.ls.return_value = [
            "test-bucket/data/files/test.txt/file1.txt",
            "test-bucket/data/files/test.txt/subdir/",
        ]

        result = await s3_node.children()

        assert len(result) == 2
        assert result[0].basename == "file1.txt"
        assert result[1].basename == "subdir"

    async def test_cloud_children_not_dir(self, s3_node, mock_fs):
        """_cloud_children() returns empty for non-directory."""
        mock_fs.isdir.return_value = False

        result = await s3_node.children()
        assert result == []

    def test_cloud_url_with_sign(self, s3_node, mock_fs):
        """_cloud_url() uses fs.sign if available."""
        mock_fs.sign.return_value = "https://signed-url.example.com/path"

        result = s3_node.url(expires_in=3600)

        assert result == "https://signed-url.example.com/path"
        mock_fs.sign.assert_called_once()

    def test_cloud_url_no_sign(self, s3_node, mock_fs):
        """_cloud_url() raises NotImplementedError if no sign method."""
        del mock_fs.sign  # Remove sign method

        with pytest.raises(NotImplementedError, match="does not support presigned URLs"):
            s3_node.url()
