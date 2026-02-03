# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""StorageNode: file/directory abstraction compatible with genro-storage API.

A StorageNode represents a file or directory in a storage backend.
It provides a unified interface for file operations regardless of backend.
"""

from __future__ import annotations

import hashlib
import hmac
import mimetypes
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fsspec import AbstractFileSystem

    from .manager import StorageManager


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class StorageNode:
    """A file or directory in a storage backend.

    Provides methods for file I/O that work with any backend (local, S3, etc.).
    API is compatible with genro-storage for future migration.
    """

    def __init__(
        self,
        manager: StorageManager,
        mount_name: str,
        path: str,
        config: dict[str, Any],
    ):
        """Initialize a storage node.

        Args:
            manager: The StorageManager that created this node.
            mount_name: Name of the mount point.
            path: Path within the mount (without mount prefix).
            config: Mount configuration dict.
        """
        self._manager = manager
        self._mount_name = mount_name
        self._path = path.lstrip("/")
        self._config = config
        self._protocol = config.get("protocol", "local")

    # ----------------------------------------------------------------- Properties (non-I/O, sync)

    @property
    def basename(self) -> str:
        """Filename with extension."""
        return Path(self._path).name

    @property
    def stem(self) -> str:
        """Filename without extension."""
        return Path(self._path).stem

    @property
    def suffix(self) -> str:
        """File extension (including dot)."""
        return Path(self._path).suffix

    @property
    def fullpath(self) -> str:
        """Full path including mount (mount:path)."""
        return f"{self._mount_name}:{self._path}"

    @property
    def path(self) -> str:
        """Path within the mount (without mount prefix)."""
        return self._path

    @property
    def mount_name(self) -> str:
        """Name of the mount point."""
        return self._mount_name

    @property
    def parent(self) -> StorageNode:
        """Parent directory node."""
        parent_path = str(Path(self._path).parent)
        if parent_path == ".":
            parent_path = ""
        return StorageNode(self._manager, self._mount_name, parent_path, self._config)

    @property
    def mimetype(self) -> str:
        """MIME type based on file extension."""
        mime, _ = mimetypes.guess_type(self.basename)
        return mime or "application/octet-stream"

    # ----------------------------------------------------------------- Navigation

    def child(self, *parts: str) -> StorageNode:
        """Get a child node by path components.

        Args:
            *parts: Path components to append.

        Returns:
            New StorageNode for the child path.
        """
        child_path = "/".join([self._path] + list(parts)) if self._path else "/".join(parts)
        return StorageNode(self._manager, self._mount_name, child_path, self._config)

    # ----------------------------------------------------------------- I/O Methods

    def _get_local_path(self) -> Path:
        """Get the local filesystem path for this node."""
        base_path = self._config.get("base_path", "")
        return Path(base_path) / self._path

    async def exists(self) -> bool:
        """Check if file/directory exists."""
        if self._protocol == "local":
            return self._get_local_path().exists()
        # Cloud backends handled by EE
        return await self._cloud_exists()

    async def is_file(self) -> bool:
        """Check if node is a file."""
        if self._protocol == "local":
            return self._get_local_path().is_file()
        return await self._cloud_is_file()

    async def is_dir(self) -> bool:
        """Check if node is a directory."""
        if self._protocol == "local":
            return self._get_local_path().is_dir()
        return await self._cloud_is_dir()

    async def size(self) -> int:
        """Get file size in bytes."""
        if self._protocol == "local":
            return self._get_local_path().stat().st_size
        return await self._cloud_size()

    async def mtime(self) -> float:
        """Get last modification time (Unix timestamp)."""
        if self._protocol == "local":
            return self._get_local_path().stat().st_mtime
        return await self._cloud_mtime()

    async def read_bytes(self) -> bytes:
        """Read entire file as bytes."""
        if self._protocol == "local":
            return self._get_local_path().read_bytes()
        return await self._cloud_read_bytes()

    async def read_text(self, encoding: str = "utf-8") -> str:
        """Read entire file as string."""
        data = await self.read_bytes()
        return data.decode(encoding)

    async def write_bytes(self, data: bytes) -> None:
        """Write bytes to file."""
        if self._protocol == "local":
            path = self._get_local_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        else:
            await self._cloud_write_bytes(data)

    async def write_text(self, text: str, encoding: str = "utf-8") -> None:
        """Write string to file."""
        await self.write_bytes(text.encode(encoding))

    async def delete(self) -> bool:
        """Delete file or directory.

        Returns:
            True if deleted, False if not found.
        """
        if self._protocol == "local":
            path = self._get_local_path()
            if path.is_file():
                path.unlink()
                return True
            elif path.is_dir():
                import shutil

                shutil.rmtree(path)
                return True
            return False
        return await self._cloud_delete()

    async def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        """Create directory."""
        if self._protocol == "local":
            self._get_local_path().mkdir(parents=parents, exist_ok=exist_ok)
        else:
            await self._cloud_mkdir(parents, exist_ok)

    async def children(self) -> list[StorageNode]:
        """List child nodes (if directory)."""
        if self._protocol == "local":
            path = self._get_local_path()
            if not path.is_dir():
                return []
            return [self.child(child.name) for child in sorted(path.iterdir())]
        return await self._cloud_children()

    async def md5hash(self) -> str:
        """Calculate MD5 hash of file content."""
        data = await self.read_bytes()
        return hashlib.md5(data).hexdigest()

    # ----------------------------------------------------------------- URLs

    def url(self, expires_in: int = 3600) -> str:
        """Generate download URL.

        For local filesystem, generates a signed token URL.
        For cloud backends, uses native presigned URLs.

        Args:
            expires_in: URL expiration in seconds.

        Returns:
            Download URL.
        """
        if self._protocol == "local":
            return self._local_signed_url(expires_in)
        return self._cloud_url(expires_in)

    def _local_signed_url(self, expires_in: int) -> str:
        """Generate signed URL for local filesystem."""
        public_base_url = self._config.get("public_base_url")
        if not public_base_url:
            raise StorageError(
                f"Mount '{self._mount_name}' requires 'public_base_url' for URL generation"
            )

        secret_key = self._config.get("secret_key", "genro-storage-default-secret")
        expires_at = int(time.time()) + expires_in
        message = f"{self._path}:{expires_at}"
        signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()[:16]

        token = f"{expires_at}-{signature}"
        return f"{public_base_url.rstrip('/')}/{self._path}?token={token}"

    def verify_url_token(self, token: str) -> bool:
        """Verify a URL token is valid and not expired.

        Args:
            token: The token from the URL query string.

        Returns:
            True if valid, False otherwise.
        """
        try:
            parts = token.split("-")
            if len(parts) != 2:
                return False

            expires_at_str, signature = parts
            expires_at = int(expires_at_str)

            if time.time() > expires_at:
                return False

            secret_key = self._config.get("secret_key", "genro-storage-default-secret")
            message = f"{self._path}:{expires_at}"
            expected_sig = hmac.new(
                secret_key.encode(), message.encode(), hashlib.sha256
            ).hexdigest()[:16]

            return hmac.compare_digest(signature, expected_sig)

        except (ValueError, IndexError):
            return False

    # ----------------------------------------------------------------- Cloud backend (S3, GCS, Azure via fsspec)

    _fs_cache: dict[str, "AbstractFileSystem"] = {}

    def _get_fs(self) -> "AbstractFileSystem":
        """Get or create fsspec filesystem for this mount."""
        if self._mount_name in self._fs_cache:
            return self._fs_cache[self._mount_name]

        try:
            import fsspec
        except ImportError as e:
            raise ImportError(
                "Cloud storage requires fsspec. "
                "Install with: pip install genro-proxy[cloud]"
            ) from e

        protocol = self._config.get("protocol", "local")

        if protocol == "s3":
            fs = fsspec.filesystem(
                "s3",
                key=self._config.get("aws_access_key_id"),
                secret=self._config.get("aws_secret_access_key"),
                endpoint_url=self._config.get("endpoint_url"),
                client_kwargs=self._config.get("client_kwargs", {}),
            )
        elif protocol == "gcs":
            fs = fsspec.filesystem(
                "gcs",
                project=self._config.get("project"),
                token=self._config.get("token"),
            )
        elif protocol == "azure":
            fs = fsspec.filesystem(
                "az",
                account_name=self._config.get("account_name"),
                account_key=self._config.get("account_key"),
                connection_string=self._config.get("connection_string"),
            )
        else:
            raise ValueError(f"Unsupported cloud protocol: {protocol}")

        self._fs_cache[self._mount_name] = fs
        return fs

    def _get_cloud_path(self) -> str:
        """Get the full path for cloud storage."""
        protocol = self._config.get("protocol")

        if protocol == "s3" or protocol == "gcs":
            bucket = self._config.get("bucket", "")
            prefix = self._config.get("prefix", "").strip("/")
            if prefix:
                return f"{bucket}/{prefix}/{self._path}"
            return f"{bucket}/{self._path}"

        elif protocol == "azure":
            container = self._config.get("container", "")
            prefix = self._config.get("prefix", "").strip("/")
            if prefix:
                return f"{container}/{prefix}/{self._path}"
            return f"{container}/{self._path}"

        return self._path

    async def _cloud_exists(self) -> bool:
        fs = self._get_fs()
        return fs.exists(self._get_cloud_path())

    async def _cloud_is_file(self) -> bool:
        fs = self._get_fs()
        return fs.isfile(self._get_cloud_path())

    async def _cloud_is_dir(self) -> bool:
        fs = self._get_fs()
        return fs.isdir(self._get_cloud_path())

    async def _cloud_size(self) -> int:
        fs = self._get_fs()
        size = fs.size(self._get_cloud_path())
        return int(size) if size is not None else 0

    async def _cloud_mtime(self) -> float:
        fs = self._get_fs()
        info = fs.info(self._get_cloud_path())
        mtime = info.get("mtime") or info.get("LastModified")
        if mtime is None:
            return 0.0
        if hasattr(mtime, "timestamp"):
            return mtime.timestamp()
        return float(mtime)

    async def _cloud_read_bytes(self) -> bytes:
        fs = self._get_fs()
        with fs.open(self._get_cloud_path(), "rb") as f:
            data = f.read()
            return data if isinstance(data, bytes) else data.encode()

    async def _cloud_write_bytes(self, data: bytes) -> None:
        fs = self._get_fs()
        cloud_path = self._get_cloud_path()

        # Ensure parent directory exists (for some backends)
        parent = "/".join(cloud_path.split("/")[:-1])
        if parent:
            fs.makedirs(parent, exist_ok=True)

        with fs.open(cloud_path, "wb") as f:
            f.write(data)  # type: ignore[arg-type]

    async def _cloud_delete(self) -> bool:
        fs = self._get_fs()
        cloud_path = self._get_cloud_path()
        if not fs.exists(cloud_path):
            return False
        if fs.isdir(cloud_path):
            fs.rm(cloud_path, recursive=True)
        else:
            fs.rm(cloud_path)
        return True

    async def _cloud_mkdir(self, parents: bool, exist_ok: bool) -> None:
        _ = parents  # fsspec makedirs handles this
        fs = self._get_fs()
        fs.makedirs(self._get_cloud_path(), exist_ok=exist_ok)

    async def _cloud_children(self) -> list[StorageNode]:
        fs = self._get_fs()
        cloud_path = self._get_cloud_path()

        if not fs.isdir(cloud_path):
            return []

        children = []
        for item in fs.ls(cloud_path, detail=False):
            # item is full path, extract just the name
            name = item.rstrip("/").split("/")[-1]
            children.append(self.child(name))

        return children

    def _cloud_url(self, expires_in: int) -> str:
        """Generate presigned URL for cloud storage."""
        fs = self._get_fs()
        cloud_path = self._get_cloud_path()

        if hasattr(fs, "sign"):
            return fs.sign(cloud_path, expiration=expires_in)

        # Fallback for backends without native signing
        raise NotImplementedError(
            f"Protocol '{self._config.get('protocol')}' does not support presigned URLs"
        )


__all__ = ["StorageNode", "StorageError"]
