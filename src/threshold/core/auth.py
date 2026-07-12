"""Credential helpers that never log or persist bearer-token plaintext."""

from hashlib import sha256
from hmac import compare_digest


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str | None, expected_digest: str) -> bool:
    if not token or not expected_digest:
        return False
    return compare_digest(token_digest(token), expected_digest)
