from __future__ import annotations

from collections.abc import Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _seed(secret: str) -> bytes:
    value = secret.encode("utf-8")
    if not value:
        raise ValueError("QQ bot AppSecret is empty")
    while len(value) < 32:
        value += value
    return value[:32]


def generate_signature(secret: str, timestamp: str, body: bytes) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(_seed(secret))
    return private_key.sign(timestamp.encode("utf-8") + body).hex()


def verify_signature(secret: str, headers: Mapping[str, str], body: bytes) -> bool:
    timestamp = headers.get("X-Signature-Timestamp", "")
    signature = headers.get("X-Signature-Ed25519", "")
    if not timestamp or not signature:
        return False
    try:
        signature_bytes = bytes.fromhex(signature)
        public_key = Ed25519PrivateKey.from_private_bytes(_seed(secret)).public_key()
        public_key.verify(signature_bytes, timestamp.encode("utf-8") + body)
    except (ValueError, TypeError):
        return False
    return True
