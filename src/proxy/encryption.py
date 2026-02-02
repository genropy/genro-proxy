# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Field-level encryption for sensitive database values.

Provides AES-256-GCM encryption for sensitive fields like passwords and API keys.
The encryption key is loaded from environment variable or secrets file.

Key sources (in priority order):
1. GENRO_PROXY_ENCRYPTION_KEY environment variable (base64-encoded)
2. /run/secrets/encryption_key file (Docker/Kubernetes secrets)

Usage:
    from proxy.encryption import encrypt_value, decrypt_value

    # Encrypt before storing
    encrypted = encrypt_value("my-secret-password")
    # Returns: "ENC:base64-encoded-ciphertext"

    # Decrypt after reading
    plaintext = decrypt_value(encrypted)
    # Returns: "my-secret-password"
"""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

# AES-GCM constants
NONCE_SIZE = 12  # 96 bits recommended for GCM
TAG_SIZE = 16  # 128 bits authentication tag
KEY_SIZE = 32  # 256 bits for AES-256

# Prefix to identify encrypted values
ENCRYPTED_PREFIX = "ENC:"

_encryption_key: bytes | None = None


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""

    pass


class EncryptionKeyNotConfigured(EncryptionError):
    """Raised when encryption key is not available."""

    pass


def _get_key() -> bytes:
    """Get or load the encryption key.

    Raises:
        EncryptionKeyNotConfigured: If no key is available.
    """
    global _encryption_key

    if _encryption_key is not None:
        return _encryption_key

    # 1. Environment variable (Kubernetes Secret / Docker env)
    key_b64 = os.environ.get("GENRO_PROXY_ENCRYPTION_KEY")
    if key_b64:
        try:
            _encryption_key = base64.b64decode(key_b64)
            if len(_encryption_key) != KEY_SIZE:
                raise EncryptionError(
                    f"GENRO_PROXY_ENCRYPTION_KEY must be {KEY_SIZE} bytes "
                    f"(got {len(_encryption_key)})"
                )
            return _encryption_key
        except Exception as e:
            raise EncryptionError(f"Invalid GENRO_PROXY_ENCRYPTION_KEY: {e}") from e

    # 2. Docker/Kubernetes secrets file
    secrets_path = Path("/run/secrets/encryption_key")
    if secrets_path.exists():
        _encryption_key = secrets_path.read_bytes().strip()
        if len(_encryption_key) != KEY_SIZE:
            raise EncryptionError(f"Encryption key in {secrets_path} must be {KEY_SIZE} bytes")
        return _encryption_key

    # 3. No key configured
    raise EncryptionKeyNotConfigured(
        "Encryption key not configured. Set GENRO_PROXY_ENCRYPTION_KEY environment "
        "variable (base64-encoded 32 bytes) or mount /run/secrets/encryption_key"
    )


def generate_key() -> str:
    """Generate a new random encryption key.

    Returns:
        Base64-encoded 32-byte key suitable for GENRO_PROXY_ENCRYPTION_KEY.
    """
    return base64.b64encode(secrets.token_bytes(KEY_SIZE)).decode()


def set_key_for_testing(key: bytes | None) -> None:
    """Set encryption key directly (for testing only).

    Args:
        key: 32-byte key or None to clear.
    """
    global _encryption_key
    if key is not None and len(key) != KEY_SIZE:
        raise ValueError(f"Key must be {KEY_SIZE} bytes")
    _encryption_key = key


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted (has ENC: prefix)."""
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value using AES-256-GCM.

    Args:
        plaintext: The value to encrypt.

    Returns:
        Encrypted value with "ENC:" prefix.

    Raises:
        EncryptionKeyNotConfigured: If no key is available.
        EncryptionError: If encryption fails.
    """
    if not plaintext:
        return plaintext

    # Already encrypted
    if is_encrypted(plaintext):
        return plaintext

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise EncryptionError(
            "Encryption requires 'cryptography' package. Install with: pip install cryptography"
        ) from e

    key = _get_key()
    nonce = secrets.token_bytes(NONCE_SIZE)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    # Format: nonce + ciphertext (includes tag)
    encrypted_data = nonce + ciphertext
    encoded = base64.b64encode(encrypted_data).decode("ascii")

    return f"{ENCRYPTED_PREFIX}{encoded}"


def decrypt_value(encrypted: str) -> str:
    """Decrypt a value encrypted with encrypt_value().

    Args:
        encrypted: The encrypted value (with "ENC:" prefix).

    Returns:
        Decrypted plaintext.

    Raises:
        EncryptionKeyNotConfigured: If no key is available.
        EncryptionError: If decryption fails.
    """
    if not encrypted:
        return encrypted

    # Not encrypted
    if not is_encrypted(encrypted):
        return encrypted

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise EncryptionError(
            "Decryption requires 'cryptography' package. Install with: pip install cryptography"
        ) from e

    key = _get_key()

    # Remove prefix and decode
    encoded = encrypted[len(ENCRYPTED_PREFIX) :]
    try:
        encrypted_data = base64.b64decode(encoded)
    except Exception as e:
        raise EncryptionError(f"Invalid encrypted data format: {e}") from e

    if len(encrypted_data) < NONCE_SIZE + TAG_SIZE:
        raise EncryptionError("Encrypted data too short")

    nonce = encrypted_data[:NONCE_SIZE]
    ciphertext = encrypted_data[NONCE_SIZE:]

    try:
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception as e:
        raise EncryptionError(f"Decryption failed: {e}") from e


def encrypt_value_with_key(plaintext: str, key: bytes) -> str:
    """Encrypt a string value using provided key.

    Same as encrypt_value() but uses an explicit key instead of global.
    Used by Table for field encryption with proxy-provided key.

    Args:
        plaintext: The value to encrypt.
        key: 32-byte AES-256 key.

    Returns:
        Encrypted value with "ENC:" prefix.
    """
    if not plaintext:
        return plaintext

    if is_encrypted(plaintext):
        return plaintext

    if len(key) != KEY_SIZE:
        raise EncryptionError(f"Key must be {KEY_SIZE} bytes")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise EncryptionError("Encryption requires 'cryptography' package") from e

    nonce = secrets.token_bytes(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    encrypted_data = nonce + ciphertext
    encoded = base64.b64encode(encrypted_data).decode("ascii")

    return f"{ENCRYPTED_PREFIX}{encoded}"


def decrypt_value_with_key(encrypted: str, key: bytes) -> str:
    """Decrypt a value using provided key.

    Same as decrypt_value() but uses an explicit key instead of global.
    Used by Table for field decryption with proxy-provided key.

    Args:
        encrypted: The encrypted value (with "ENC:" prefix).
        key: 32-byte AES-256 key.

    Returns:
        Decrypted plaintext.
    """
    if not encrypted:
        return encrypted

    if not is_encrypted(encrypted):
        return encrypted

    if len(key) != KEY_SIZE:
        raise EncryptionError(f"Key must be {KEY_SIZE} bytes")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise EncryptionError("Decryption requires 'cryptography' package") from e

    encoded = encrypted[len(ENCRYPTED_PREFIX) :]
    try:
        encrypted_data = base64.b64decode(encoded)
    except Exception as e:
        raise EncryptionError(f"Invalid encrypted data format: {e}") from e

    if len(encrypted_data) < NONCE_SIZE + TAG_SIZE:
        raise EncryptionError("Encrypted data too short")

    nonce = encrypted_data[:NONCE_SIZE]
    ciphertext = encrypted_data[NONCE_SIZE:]

    try:
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception as e:
        raise EncryptionError(f"Decryption failed: {e}") from e


class EncryptionManager:
    """Manager for encryption key loading and operations.

    Loads encryption key from environment variable or secrets file.
    Follows the parent=proxy pattern like other managers.

    Attributes:
        proxy: Parent proxy instance.
        key: Loaded encryption key (32 bytes) or None.
    """

    def __init__(self, parent: "object", env_var: str = "PROXY_ENCRYPTION_KEY"):
        """Initialize encryption manager.

        Args:
            parent: Proxy instance (provides context).
            env_var: Environment variable name for base64-encoded key.
        """
        self.proxy = parent
        self._env_var = env_var
        self._key: bytes | None = None
        self._load_key()

    def _load_key(self) -> None:
        """Load encryption key from environment or secrets file."""
        # 1. Environment variable (base64-encoded)
        key_b64 = os.environ.get(self._env_var)
        if key_b64:
            try:
                key = base64.b64decode(key_b64)
                if len(key) == KEY_SIZE:
                    self._key = key
                    return
            except Exception:
                pass

        # 2. Docker/Kubernetes secrets file
        secrets_path = Path("/run/secrets/encryption_key")
        if secrets_path.exists():
            try:
                key = secrets_path.read_bytes().strip()
                if len(key) == KEY_SIZE:
                    self._key = key
                    return
            except Exception:
                pass

    @property
    def key(self) -> bytes | None:
        """Encryption key (32 bytes) or None if not configured."""
        return self._key

    @property
    def is_configured(self) -> bool:
        """True if encryption key is available."""
        return self._key is not None

    def set_key(self, key: bytes) -> None:
        """Set encryption key programmatically (for testing)."""
        if len(key) != KEY_SIZE:
            raise ValueError(f"Encryption key must be {KEY_SIZE} bytes")
        self._key = key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a value using the configured key."""
        if self._key is None:
            raise EncryptionKeyNotConfigured("Encryption key not configured")
        return encrypt_value_with_key(plaintext, self._key)

    def decrypt(self, encrypted: str) -> str:
        """Decrypt a value using the configured key."""
        if self._key is None:
            raise EncryptionKeyNotConfigured("Encryption key not configured")
        return decrypt_value_with_key(encrypted, self._key)


__all__ = [
    "ENCRYPTED_PREFIX",
    "EncryptionError",
    "EncryptionKeyNotConfigured",
    "EncryptionManager",
    "decrypt_value",
    "decrypt_value_with_key",
    "encrypt_value",
    "encrypt_value_with_key",
    "generate_key",
    "is_encrypted",
    "set_key_for_testing",
]
