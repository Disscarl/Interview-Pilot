"""Auth primitives: password hashing + HS256 JWT (stdlib only)."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from config import settings

_PBKDF2_ITERATIONS = 600_000
# Iterations used before R13 — kept so pre-upgrade password hashes still verify.
_LEGACY_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """Hash a password as '<iterations>$<salt_hex>$<hash_hex>' using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time password verification (accepts legacy 2-part hashes)."""
    try:
        parts = stored.split("$")
        if len(parts) == 3:
            iterations = int(parts[0])
            salt_hex, hash_hex = parts[1], parts[2]
        elif len(parts) == 2:
            # Pre-R13 format: '<salt_hex>$<hash_hex>' (fixed 100k iterations).
            iterations = _LEGACY_PBKDF2_ITERATIONS
            salt_hex, hash_hex = parts
        else:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), iterations
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user_id: int, expires_days: int | None = None) -> str:
    """Create a signed HS256 JWT with sub/iat/jti/exp claims."""
    expires_days = expires_days or settings.jwt_expires_days
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "iat": now,
        "jti": secrets.token_hex(8),
        "exp": now + expires_days * 86400,
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    sig = hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


def decode_token(token: str) -> int | None:
    """Verify an HS256 JWT and return its user_id, or None if invalid/expired."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        return None
    signing_input = f"{header_b64}.{payload_b64}"
    expected = hmac.new(
        settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    try:
        provided = _b64url_decode(sig_b64)
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
