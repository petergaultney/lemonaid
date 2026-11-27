"""A browser's push subscription, with real keys."""

import base64
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def subscription(endpoint: str = "https://push.example/ada") -> dict:
    """As a browser's `PushSubscription.toJSON()` gives it."""
    point = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    return {"endpoint": endpoint, "keys": {"p256dh": _b64(point), "auth": _b64(os.urandom(16))}}
