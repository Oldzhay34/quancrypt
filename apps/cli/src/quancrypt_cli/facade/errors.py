"""The one error the CLI sees: the facade translates the errors of the deeper layers into it."""

from __future__ import annotations


class CliError(Exception):
    """A failure the user can act on. `code` selects the message; `detail` is safe to show (no token, no body)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail
