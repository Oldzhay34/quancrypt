"""The local session token (FR-02, guardrails-security section 6): 32 random bytes, base64url without padding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from quancrypt_cli.domain.errors import InvalidSessionTokenError

TOKEN_BYTES = 32
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")  # 32 bytes in base64url are 43 characters


@dataclass(frozen=True)
class SessionToken:
    """A secret: it never shows in `repr`, `str`, logs or error messages."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not _TOKEN.fullmatch(self.value):
            raise InvalidSessionTokenError("a session token is 43 base64url characters")

    def __repr__(self) -> str:
        return "SessionToken(***)"

    def __str__(self) -> str:
        return "***"
