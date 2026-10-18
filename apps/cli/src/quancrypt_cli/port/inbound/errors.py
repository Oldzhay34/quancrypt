"""Errors of the inbound use cases (in port.inbound so that the facade can translate them)."""

from __future__ import annotations


class InvalidProjectError(Exception):
    """The directory cannot be set up. `reason` is `not-a-directory`, `no-build-file` or `ambiguous`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class NotInitializedError(Exception):
    """The project has no `.quancrypt/` yet: run `quancrypt init`."""


class ComposeFailedError(Exception):
    """`docker compose` failed; the message is the safe summary."""


class ServicesNotReadyError(Exception):
    """The containers started but a required service did not answer in time. `names` lists them."""

    def __init__(self, names: tuple[str, ...]) -> None:
        super().__init__(", ".join(names))
        self.names = names


class RegistrationFailedError(Exception):
    """core-service did not register the project. `kind` is `unreachable`, `unauthorized` or `rejected`."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class StateError(Exception):
    """`.quancrypt/` could not be read or written."""
