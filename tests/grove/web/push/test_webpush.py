"""A Web Push message decrypts as a browser decrypts it, and its VAPID signature verifies."""

import base64
import json
import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from lemonaid.grove.web.push import webpush


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _point(key) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def _hkdf(salt: bytes, info: bytes, length: int, secret: bytes) -> bytes:
    return HKDF(hashes.SHA256(), length, salt, info).derive(secret)


def _browser_decrypts(body: bytes, private, auth: bytes) -> bytes:
    """RFC 8291 from the receiving side."""
    salt, (rs, idlen) = body[:16], struct.unpack(">IB", body[16:21])
    theirs, sealed = body[21 : 21 + idlen], body[21 + idlen :]
    assert rs == 4096
    shared = private.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), theirs)
    )
    ikm = _hkdf(auth, b"WebPush: info\x00" + _point(private.public_key()) + theirs, 32, shared)
    key = _hkdf(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    plain = AESGCM(key).decrypt(nonce, sealed, None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


def test_a_message_decrypts_as_the_browser_decrypts_it():
    private, auth = ec.generate_private_key(ec.SECP256R1()), b"0123456789abcdef"
    to = webpush.Subscription(
        "https://push.example/abc", _b64(_point(private.public_key())), _b64(auth)
    )

    body = webpush.encrypt(json.dumps({"title": "Ada"}).encode(), to)

    assert json.loads(_browser_decrypts(body, private, auth)) == {"title": "Ada"}


def test_the_vapid_header_names_the_key_and_its_signature_verifies():
    pem = webpush.new_key()

    header = webpush._vapid("https://push.example/send/abc", pem)

    token, key = header.removeprefix("vapid t=").split(", k=")
    assert key == webpush.public_key(pem)
    signed, signature = token.rsplit(".", 1)
    claims = json.loads(_unb64(signed.split(".")[1]))
    assert claims["aud"] == "https://push.example"
    raw = _unb64(signature)
    der = utils.encode_dss_signature(
        int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
    )
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _unb64(key))
    public.verify(der, signed.encode(), ec.ECDSA(hashes.SHA256()))  # raises if it doesn't
