"""Token generator adapter: the `secrets` module (a cryptographically secure source)."""

from __future__ import annotations

import secrets

from quancrypt_cli.domain.session_token import TOKEN_BYTES, SessionToken


class SecretsTokenGenerator:
    """Implements TokenGenerator: 32 random bytes in base64url without padding."""

    def generate(self) -> SessionToken:
        return SessionToken(secrets.token_urlsafe(TOKEN_BYTES))
