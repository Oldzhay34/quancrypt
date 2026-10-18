"""Outbound port: new session tokens."""

from __future__ import annotations

from typing import Protocol

from quancrypt_cli.domain.session_token import SessionToken


class TokenGenerator(Protocol):
    def generate(self) -> SessionToken:
        """A new unpredictable token (32 random bytes, base64url)."""
        ...
