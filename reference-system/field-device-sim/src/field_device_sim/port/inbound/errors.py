"""Errors of the inbound use cases (in port.inbound so that the facade can translate them)."""

from __future__ import annotations


class InvalidRequestError(Exception):
    """The command is invalid or yields an invalid transaction."""


class DeliveryFailedError(Exception):
    """The transaction could not be delivered to the broker."""
