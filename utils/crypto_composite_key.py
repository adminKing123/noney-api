"""
secure_composite_id.py

Create a secure reversible composite ID from two IDs using authenticated encryption.
Tamper-proof, URL safe, and requires secret key to decode.
"""

from __future__ import annotations

import base64
import os
from hashlib import scrypt
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import CONFIG

# ================= CONFIG =================
# In production load from environment variables
_SECRET_KEY = CONFIG.CRYPTOCOMPOSITEKEY.SECRET_KEY
_SALT = CONFIG.CRYPTOCOMPOSITEKEY.SALT
_SEPARATOR = CONFIG.CRYPTOCOMPOSITEKEY.SEPARATOR
_NONCE_SIZE = CONFIG.CRYPTOCOMPOSITEKEY.NONCE_SIZE


def _derive_key(secret: bytes, salt: bytes) -> bytes:
    """Derive a 32-byte AES key using scrypt KDF."""
    return scrypt(secret, salt=salt, n=2**14, r=8, p=1, dklen=32)


_KEY = _derive_key(_SECRET_KEY, _SALT)


# =========================================================
# PUBLIC API
# =========================================================

def create_composite_id(primary_id: str, secondary_id: str) -> str:
    """
    Combine two IDs into a single secure composite ID.

    The returned ID:
        - Is URL safe
        - Cannot be forged or modified
        - Requires the secret key to decode
        - Is fully reversible

    Args:
        primary_id: First identifier
        secondary_id: Second identifier

    Returns:
        Encrypted composite ID string
    """

    if not isinstance(primary_id, str) or not isinstance(secondary_id, str):
        raise TypeError("IDs must be strings")

    packed = f"{len(primary_id)}{_SEPARATOR}{primary_id}{secondary_id}".encode()

    aes = AESGCM(_KEY)
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = aes.encrypt(nonce, packed, None)

    token = base64.urlsafe_b64encode(nonce + ciphertext).decode()
    return token


def parse_composite_id(composite_id: str) -> Tuple[str, str]:
    """
    Decode a composite ID back into the original two IDs.

    Args:
        composite_id: The encrypted ID created by create_composite_id()

    Returns:
        Tuple (primary_id, secondary_id)

    Raises:
        ValueError: If token invalid or tampered
    """

    try:
        raw = base64.urlsafe_b64decode(composite_id.encode())
        nonce = raw[:_NONCE_SIZE]
        ciphertext = raw[_NONCE_SIZE:]

        aes = AESGCM(_KEY)
        packed = aes.decrypt(nonce, ciphertext, None).decode()

        length_str, rest = packed.split(_SEPARATOR, 1)
        length = int(length_str)

        primary_id = rest[:length]
        secondary_id = rest[length:]

        return primary_id, secondary_id

    except Exception as exc:
        raise ValueError("Invalid or corrupted composite ID") from exc