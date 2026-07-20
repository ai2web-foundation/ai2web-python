"""AP2 (Agent Payments Protocol, Google - v0.2.0) merchant primitives.

AP2 is mandate-based: the merchant prices a buyer agent's Intent Mandate as a CartContents
(a W3C PaymentRequest, amounts in decimal major units) and digitally *signs* it into a
CartMandate - a short-lived guarantee of items and price - then settles a user-signed Payment
Mandate. This module provides the reusable, app-agnostic core: build an Intent Mandate, build a
CartContents from line items, sign it as an RS256 JWT (``cart_hash`` over the canonical contents),
publish the public key as a JWKS, verify a Cart Mandate, and parse a Payment Mandate.

Pricing a cart is application-specific, so this stays a pure toolkit - it does not fetch a
catalogue or serve routes. RS256 signing is implemented in pure standard library (ASN.1 DER key
parsing + modular exponentiation), so the SDK keeps zero third-party dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Union

EXTENSION_URI = "https://github.com/google-agentic-commerce/ap2/v1"
VERSION = "0.2.0"
_DEFAULT_TTL = 900
# DigestInfo prefix for SHA-256 (EMSA-PKCS1-v1_5).
_SHA256_DER_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


# --- public API --------------------------------------------------------------

def transport(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The ``transports.ap2`` advertisement to merge into a manifest."""
    block = {
        "enabled": True,
        "version": VERSION,
        "extension": EXTENSION_URI,
        "agent_card": "/ai2w/ap2/agent-card",
        "cart": "/ai2w/ap2/cart",
        "payment": "/ai2w/ap2/payment",
        "jwks": "/ai2w/ap2/jwks",
    }
    if overrides:
        block.update(overrides)
    return block


def intent_mandate(
    description: str,
    *,
    merchants: Optional[List[str]] = None,
    skus: Optional[List[str]] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    requires_refundability: bool = False,
    user_cart_confirmation_required: bool = True,
    expires_in: int = _DEFAULT_TTL,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    """Build an AP2 IntentMandate (classic v0.2.0 shape)."""
    ts = int(now if now is not None else time.time())
    intent: Dict[str, Any] = {
        "natural_language_description": description,
        "intent_expiry": _iso(ts + expires_in),
        "user_cart_confirmation_required": bool(user_cart_confirmation_required),
    }
    if merchants:
        intent["merchants"] = list(merchants)
    if skus:
        intent["skus"] = list(skus)
    if items:
        intent["items"] = list(items)
    if requires_refundability:
        intent["requires_refundability"] = True
    return intent


def amount(value: float, currency: str) -> Dict[str, Any]:
    """AP2 PaymentCurrencyAmount: decimal major units, ISO 4217."""
    return {"currency": currency.upper(), "value": round(float(value), 2)}


def cart_contents(
    items: List[Dict[str, Any]],
    currency: str,
    merchant_name: str,
    *,
    id: Optional[str] = None,
    payment_details_id: Optional[str] = None,
    method_data: Optional[List[Dict[str, Any]]] = None,
    user_cart_confirmation_required: bool = True,
    expires_in: int = _DEFAULT_TTL,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a CartContents (W3C PaymentRequest) from line items.

    Each item is ``{"label": str, "unit_amount": float, "quantity": int = 1}``.
    """
    ts = int(now if now is not None else time.time())
    display: List[Dict[str, Any]] = []
    total = 0.0
    for it in items:
        qty = max(1, int(it.get("quantity", 1)))
        unit = float(it.get("unit_amount", it.get("amount", 0)))
        line = unit * qty
        label = str(it.get("label", "Item"))
        if qty > 1:
            label = f"{label} x{qty}"
        display.append({"label": label, "amount": amount(line, currency)})
        total += line
    return {
        "id": id or ("cart_" + secrets.token_hex(10)),
        "user_cart_confirmation_required": bool(user_cart_confirmation_required),
        "payment_request": {
            "method_data": method_data or [{"supported_methods": "card", "data": {}}],
            "details": {
                "id": payment_details_id or ("pr_" + secrets.token_hex(10)),
                "display_items": display,
                "total": {"label": "Total", "amount": amount(total, currency)},
            },
            "options": {"request_shipping": True},
        },
        "cart_expiry": _iso(ts + expires_in),
        "merchant_name": merchant_name,
    }


def sign_cart(
    contents: Dict[str, Any],
    private_key_pem: str,
    *,
    kid: Optional[str] = None,
    iss: Optional[str] = None,
    aud: str = "ap2-network",
    expires_in: int = _DEFAULT_TTL,
    now: Optional[int] = None,
) -> str:
    """The ``merchant_authorization`` JWT (RS256) over the canonical CartContents."""
    n, e, d = _parse_private_pem(private_key_pem)
    ts = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT", "kid": kid or _kid(n, e)}
    claims = {
        "iss": iss if iss is not None else contents.get("merchant_name", ""),
        "sub": contents.get("id", ""),
        "aud": aud,
        "iat": ts,
        "exp": ts + expires_in,
        "jti": secrets.token_hex(12),
        "cart_hash": _b64url(hashlib.sha256(_canonical(contents)).digest()),
    }
    signing_input = (_b64url(_canonical(header)) + "." + _b64url(_canonical(claims))).encode()
    sig = _rsa_sign(signing_input, n, d)
    return signing_input.decode() + "." + _b64url(sig)


def cart_mandate(contents: Dict[str, Any], private_key_pem: str, **opts: Any) -> Dict[str, Any]:
    """Sign CartContents into a CartMandate (``contents`` + ``merchant_authorization``)."""
    return {"contents": contents, "merchant_authorization": sign_cart(contents, private_key_pem, **opts)}


def jwks(private_key_pem: str, *, kid: Optional[str] = None) -> Dict[str, Any]:
    """JWKS publishing the cart-signing public key, for verifiers."""
    n, e, _ = _parse_private_pem(private_key_pem)
    return {"keys": [{
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid or _kid(n, e),
        "n": _b64url(_int_to_bytes(n)),
        "e": _b64url(_int_to_bytes(e)),
    }]}


def verify_cart_mandate(mandate: Dict[str, Any], key: Union[str, Dict[str, Any]]) -> bool:
    """Verify a CartMandate's signature and cart_hash binding, and that it has not expired.

    ``key`` is either a private-key PEM (public part derived) or a JWK dict ``{"n", "e"}``
    (e.g. one entry from :func:`jwks`).
    """
    jwt = mandate.get("merchant_authorization", "")
    parts = jwt.split(".")
    if len(parts) != 3:
        return False
    h, p, s = parts
    if isinstance(key, dict):
        n = int.from_bytes(_b64url_decode(key["n"]), "big")
        e = int.from_bytes(_b64url_decode(key["e"]), "big")
    else:
        n, e, _ = _parse_private_pem(key)
    if not _rsa_verify(f"{h}.{p}".encode(), _b64url_decode(s), n, e):
        return False
    try:
        claims = json.loads(_b64url_decode(p))
    except ValueError:
        return False
    if not claims.get("cart_hash"):
        return False
    if "exp" in claims and time.time() > int(claims["exp"]):
        return False
    expected = _b64url(hashlib.sha256(_canonical(mandate.get("contents", {}))).digest())
    return secrets.compare_digest(str(claims["cart_hash"]), expected)


def payment_details(payment_mandate: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the salient fields of a PaymentMandate for settlement."""
    c = payment_mandate.get("payment_mandate_contents") or {}
    resp = c.get("payment_response") or {}
    total = c.get("payment_details_total") or {}
    return {
        "payment_mandate_id": c.get("payment_mandate_id"),
        "payment_details_id": c.get("payment_details_id"),
        "total": total.get("amount"),
        "method": resp.get("method_name"),
        "payer_email": resp.get("payer_email"),
        "payer_name": resp.get("payer_name"),
    }


# --- pure-stdlib RSA / encoding helpers --------------------------------------

def canonical(data: Any) -> str:
    """JCS (RFC 8785) canonicalisation, so a cart_hash is byte-identical across every SDK:
    object keys sorted, no whitespace, minimal string escaping, integers without a decimal
    point, currency amounts as a short decimal."""
    if data is None:
        return "null"
    if data is True:
        return "true"
    if data is False:
        return "false"
    if isinstance(data, int):
        return str(data)
    if isinstance(data, float):
        return _jcs_number(data)
    if isinstance(data, str):
        return _jcs_string(data)
    if isinstance(data, (list, tuple)):
        return "[" + ",".join(canonical(x) for x in data) + "]"
    if isinstance(data, dict):
        keys = sorted(str(k) for k in data.keys())
        return "{" + ",".join(_jcs_string(k) + ":" + canonical(data[k]) for k in keys) + "}"
    return "null"


def _canonical(data: Any) -> bytes:
    return canonical(data).encode("utf-8")


def _jcs_number(x: float) -> str:
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _jcs_string(s: str) -> str:
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif o == 0x08:
            out.append("\\b")
        elif o == 0x09:
            out.append("\\t")
        elif o == 0x0A:
            out.append("\\n")
        elif o == 0x0C:
            out.append("\\f")
        elif o == 0x0D:
            out.append("\\r")
        elif o < 0x20:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _int_to_bytes(x: int) -> bytes:
    return x.to_bytes((x.bit_length() + 7) // 8 or 1, "big")


def _kid(n: int, e: int) -> str:
    return hashlib.sha256(_int_to_bytes(n) + _int_to_bytes(e)).hexdigest()[:16]


def _iso(ts: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts))


def _emsa_pkcs1_v15(message: bytes, k: int) -> bytes:
    digest = hashlib.sha256(message).digest()
    t = _SHA256_DER_PREFIX + digest
    ps = b"\xff" * (k - len(t) - 3)
    return b"\x00\x01" + ps + b"\x00" + t


def _rsa_sign(message: bytes, n: int, d: int) -> bytes:
    k = (n.bit_length() + 7) // 8
    em = _emsa_pkcs1_v15(message, k)
    sig = pow(int.from_bytes(em, "big"), d, n)
    return sig.to_bytes(k, "big")


def _rsa_verify(message: bytes, signature: bytes, n: int, e: int) -> bool:
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    em = pow(int.from_bytes(signature, "big"), e, n).to_bytes(k, "big")
    return secrets.compare_digest(em, _emsa_pkcs1_v15(message, k))


# --- minimal ASN.1 DER parsing (PKCS#8 / PKCS#1 RSA private keys) -------------

def _der_len(data: bytes, i: int):
    b = data[i]
    i += 1
    if b < 0x80:
        return b, i
    count = b & 0x7F
    length = int.from_bytes(data[i:i + count], "big")
    return length, i + count


def _der_tlv(data: bytes, i: int):
    tag = data[i]
    i += 1
    length, i = _der_len(data, i)
    return tag, data[i:i + length], i + length


def _der_int(data: bytes, i: int):
    _tag, val, i = _der_tlv(data, i)
    return int.from_bytes(val, "big"), i


def _parse_private_pem(pem: str) -> "tuple[int, int, int]":
    """Return (n, e, d) from a PKCS#8 or PKCS#1 RSA private-key PEM. Pure stdlib."""
    body = "".join(
        line for line in pem.splitlines() if line and not line.startswith("-----")
    )
    der = base64.b64decode(body)
    _tag, seq, _ = _der_tlv(der, 0)  # outer SEQUENCE
    # PKCS#1 "RSA PRIVATE KEY" starts SEQUENCE{ version, n, e, d, ... }.
    # PKCS#8 "PRIVATE KEY" wraps it: SEQUENCE{ version, algId, OCTET STRING{ RSAPrivateKey } }.
    if "BEGIN RSA PRIVATE KEY" in pem:
        rsa = seq
    else:
        i = 0
        _ver, i = _der_int(seq, i)          # version
        _tag, _alg, i = _der_tlv(seq, i)    # AlgorithmIdentifier
        _tag, rsa, i = _der_tlv(seq, i)     # privateKey OCTET STRING (contains RSAPrivateKey)
        _tag, rsa, _ = _der_tlv(rsa, 0)     # inner RSAPrivateKey SEQUENCE
    j = 0
    _ver, j = _der_int(rsa, j)
    n, j = _der_int(rsa, j)
    e, j = _der_int(rsa, j)
    d, j = _der_int(rsa, j)
    return n, e, d
