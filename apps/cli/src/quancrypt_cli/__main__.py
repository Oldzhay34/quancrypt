"""Entry point: `quancrypt` (and `python -m quancrypt_cli`). Outside the layers, so it may wire them."""

import os
import sys

import typer

from quancrypt_cli.api.commands import build_app
from quancrypt_cli.api.messages import language_from, text
from quancrypt_cli.infrastructure.container import build_facade
from quancrypt_cli.infrastructure.settings import LANGUAGE_VARIABLE


def main() -> None:
    language = language_from(os.environ.get(LANGUAGE_VARIABLE))
    app = build_app(lambda: build_facade(os.environ), language)
    try:
        app()
    except Exception as error:  # noqa: BLE001 - last resort: only the class name is shown, never a message or locals
        typer.echo(text(language, "error", text=text(language, "unexpected", detail=type(error).__name__)), err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
