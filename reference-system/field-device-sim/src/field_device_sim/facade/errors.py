"""Errors the CLI sees; the facade translates the errors of the deeper layers into them."""

from __future__ import annotations


class PublishFailedError(Exception):
    """A transaction could not be created or delivered; the message is safe to log."""
