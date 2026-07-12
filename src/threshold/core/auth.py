"""Credential helpers that never log or persist bearer-token plaintext."""

from hashlib import sha256
from hmac import compare_digest


MIN_BEARER_TOKEN_LENGTH = 32
MAX_BEARER_TOKEN_LENGTH = 512


def is_valid_bearer_token(token: str | None) -> bool:
    """Accept bounded visible ASCII suitable for an HTTP bearer header."""

    return bool(
        token
        and MIN_BEARER_TOKEN_LENGTH <= len(token) <= MAX_BEARER_TOKEN_LENGTH
        and all(0x21 <= ord(character) <= 0x7E for character in token)
    )


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str | None, expected_digest: str) -> bool:
    if not token or not expected_digest:
        return False
    return compare_digest(token_digest(token), expected_digest)
