"""Sending one Web Push message: encrypted to the browser (RFC 8291) and signed by the server (VAPID,
RFC 8292), posted to the push service the browser named when it subscribed.

The push service (Google's, for Chrome on Android) sees only the message's size and timing.
"""

import base64
import json
import os
import struct
import time
import typing as ty
import urllib.error
import urllib.parse
import urllib.request

try:  # the `push` extra
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError:
    ec = None  # type: ignore[assignment]

MISSING = "push notifications need the `push` extra: pip install 'lemonaid-inbox[push]'"
CONTACT = "https://github.com/petergaultney/lemonaid"  # VAPID's `sub`: who runs this sender
TTL_SECONDS = 24 * 3600  # a phone that's off longer than this misses the message
_RECORD = 4096


class Subscription(ty.NamedTuple):
    endpoint: str
    p256dh: str  # the browser's public key, base64url
    auth: str  # its shared secret, base64url


class Gone(Exception):
    """The push service no longer knows the subscription: the browser dropped it."""


def available() -> bool:
    return ec is not None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def new_key() -> bytes:
    return ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _point(key: "ec.EllipticCurvePublicKey") -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def public_key(pem: bytes) -> str:
    """The key a page subscribes with (`applicationServerKey`), base64url."""
    return _b64(_point(serialization.load_pem_private_key(pem, None).public_key()))


def _hkdf(salt: bytes, info: bytes, length: int, secret: bytes) -> bytes:
    return HKDF(hashes.SHA256(), length, salt, info).derive(secret)


def check(to: Subscription) -> None:
    """Raises ValueError unless *to*'s keys are a P-256 point and a 16-byte secret, as a browser's
    are, so that `encrypt` can't fail on them later."""
    try:
        theirs, secret = _unb64(to.p256dh), _unb64(to.auth)
    except (ValueError, TypeError) as error:  # binascii.Error is a ValueError
        raise ValueError(f"a push key isn't base64url: {error}") from error

    if len(secret) != 16:
        raise ValueError("a push subscription's auth secret is 16 bytes")
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), theirs)  # ValueError if not


def encrypt(plain: bytes, to: Subscription, salt: bytes | None = None) -> bytes:
    theirs = _unb64(to.p256dh)
    mine = ec.generate_private_key(ec.SECP256R1())
    ours = _point(mine.public_key())
    shared = mine.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), theirs)
    )
    salt = salt or os.urandom(16)
    ikm = _hkdf(_unb64(to.auth), b"WebPush: info\x00" + theirs + ours, 32, shared)
    key = _hkdf(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    sealed = AESGCM(key).encrypt(nonce, plain + b"\x02", None)
    return salt + struct.pack(">IB", _RECORD, len(ours)) + ours + sealed


def _vapid(endpoint: str, pem: bytes) -> str:
    """The Authorization header that signs a post to *endpoint*'s push service."""
    private = serialization.load_pem_private_key(pem, None)
    where = urllib.parse.urlsplit(endpoint)
    claims = {
        "aud": f"{where.scheme}://{where.netloc}",
        "exp": int(time.time()) + 12 * 3600,
        "sub": CONTACT,
    }
    signed = ".".join(
        _b64(json.dumps(part, separators=(",", ":")).encode())
        for part in ({"typ": "JWT", "alg": "ES256"}, claims)
    )
    r, s = utils.decode_dss_signature(private.sign(signed.encode(), ec.ECDSA(hashes.SHA256())))
    token = f"{signed}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={public_key(pem)}"


def send(
    to: Subscription, message: dict, pem: bytes, urgent: bool = False, topic: str = ""
) -> None:
    """Post *message* as JSON. Raises Gone when the browser has dropped the subscription, and
    OSError when the push service can't be reached or refuses it otherwise.

    A later message with the same *topic* replaces one the phone hasn't fetched yet."""
    request = urllib.request.Request(
        to.endpoint,
        data=encrypt(json.dumps(message).encode(), to),
        method="POST",
        headers={
            "Authorization": _vapid(to.endpoint, pem),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(TTL_SECONDS),
            "Urgency": "high" if urgent else "normal",
            **({"Topic": topic} if topic else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return

    except urllib.error.HTTPError as error:
        if error.code in (404, 410):
            raise Gone(to.endpoint) from error

        raise OSError(
            f"the push service refused it: {error.code} {error.read()[:200]!r}"
        ) from error
