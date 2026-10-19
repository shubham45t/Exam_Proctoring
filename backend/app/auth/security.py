"""Authentication security: standard PBKDF2 password hashing & HMAC-SHA256 token signing.
No external native C-extensions or compilation required.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

# Default secret for token signing (override via OMNI_SECRET_KEY or config)
DEFAULT_SECRET = "omniproctor-secure-jwt-replacement-key-32-chars-minimum"
TOKEN_EXPIRY_SECONDS = 86400 * 7  # 7 days


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"pbkdf2_sha256$100000${salt}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored PBKDF2 hash."""
    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_key = parts[3]
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(key.hex(), expected_key)
    except Exception:
        return False


def create_access_token(payload: dict[str, Any], secret: str = DEFAULT_SECRET, expires_in: int = TOKEN_EXPIRY_SECONDS) -> str:
    """Create a URL-safe signed bearer token."""
    claims = dict(payload)
    claims["exp"] = int(time.time()) + expires_in
    claims["iat"] = int(time.time())
    
    payload_json = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    
    return f"{payload_b64}.{sig_b64}"


def decode_access_token(token: str, secret: str = DEFAULT_SECRET) -> dict[str, Any] | None:
    """Decode and verify token signature and expiration. Returns claims dict or None."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts[0], parts[1]
        
        # Verify signature
        expected_sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
            
        # Decode claims
        payload_json = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        claims = json.loads(payload_json.decode("utf-8"))
        
        # Check expiry
        if "exp" in claims and time.time() > claims["exp"]:
            return None
            
        return claims
    except Exception:
        return None
