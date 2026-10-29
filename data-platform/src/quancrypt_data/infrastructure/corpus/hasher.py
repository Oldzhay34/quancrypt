from __future__ import annotations

from quancrypt_data.domain.corpus_events import project_key


class HmacProjectKeyHasher:
    """HMAC-SHA256 with QUANCRYPT_ANON_SALT as the key (the salt text in UTF-8), like core-service's
    HmacEventAnonymizer."""

    def __init__(self, salt: str) -> None:
        if len(salt) < 32 or "CHANGE_ME" in salt:
            raise ValueError("the anonymisation salt must be at least 32 characters and not the placeholder")
        self._salt = salt

    def key_for(self, identifier: str) -> str:
        return project_key(self._salt, identifier)

    def __repr__(self) -> str:
        return "HmacProjectKeyHasher(salt=<hidden>)"
