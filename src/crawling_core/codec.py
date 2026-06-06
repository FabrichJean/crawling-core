"""Pluggable request/response codecs.

Some platforms send plain JSON; others wrap everything in an encrypted
envelope (AES, custom signing, ...). The pipeline and transport layer don't
care which — they just call ``encode_request``/``decode_response`` on
whatever :class:`Codec` the adapter provides.

``NoopCodec`` covers plain-JSON platforms. ``AesCfbCodec`` is a ready-made
implementation for the common "AES-CFB payload + signed envelope" scheme
seen across several PWA sites; adapters for sites with a different scheme
should implement their own :class:`Codec`.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Codec(Protocol):
    def encode_request(self, payload: dict[str, Any]) -> Any:
        """Turn a plain payload dict into whatever the transport should send."""

    def decode_response(self, raw: Any) -> dict[str, Any] | None:
        """Turn a raw response body into a plain payload dict, or None on failure."""


class NoopCodec:
    """Pass-through codec for platforms that speak plain JSON."""

    def encode_request(self, payload: dict[str, Any]) -> Any:
        return payload

    def decode_response(self, raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (str, bytes, bytearray)):
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return None
        return None


class AesCfbCodec:
    """AES-CFB envelope codec: ``client=<id>&timestamp=<ts>&data=<hex>&sign=<md5(sha256)>``.

    This mirrors the scheme several PWA sites use. Construct one per
    platform with that platform's key/iv/client id; if a platform's
    envelope differs (different sign formula, CBC instead of CFB, extra
    fields, ...), write a small platform-specific :class:`Codec` instead of
    forcing it through here.
    """

    def __init__(
        self,
        *,
        key: bytes,
        iv: bytes,
        client: str = "pwa",
        sign_secret: bytes | None = None,
        segment_size: int = 128,
    ) -> None:
        from Crypto.Cipher import AES  # imported lazily: optional dependency

        self._aes = AES
        self.key = key
        self.iv = iv
        self.client = client
        self.sign_secret = (sign_secret or key).decode("utf-8")
        self.segment_size = segment_size

    def _cipher(self):
        return self._aes.new(
            self.key, self._aes.MODE_CFB, iv=self.iv, segment_size=self.segment_size
        )

    def _sign(self, encrypted_hex: str, timestamp: int) -> str:
        sign_base = (
            f"client={self.client}&data={encrypted_hex}"
            f"&timestamp={timestamp}{self.sign_secret}"
        )
        inner = hashlib.sha256(sign_base.encode("utf-8")).hexdigest()
        return hashlib.md5(inner.encode("utf-8")).hexdigest()

    def encode_request(self, payload: dict[str, Any]) -> str:
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encrypted_hex = self._cipher().encrypt(plaintext).hex().upper()
        timestamp = int(time.time())
        sign = self._sign(encrypted_hex, timestamp)
        return f"client={self.client}&timestamp={timestamp}&data={encrypted_hex}&sign={sign}"

    def decode_response(self, raw: Any) -> dict[str, Any] | None:
        try:
            if isinstance(raw, dict):
                raw = raw.get("data", "")
            cleaned = str(raw).strip().replace("\n", "").replace("\r", "")
            if cleaned.startswith("0x"):
                cleaned = cleaned[2:]
            ciphertext = bytes.fromhex(cleaned)
            plaintext = self._cipher().decrypt(ciphertext)
            return json.loads(plaintext.decode("utf-8"))
        except Exception:
            return None
