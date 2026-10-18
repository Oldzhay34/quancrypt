"""The Typer commands of `quancrypt`. They talk to the facade only and print its answers."""

from collections.abc import Callable
from typing import Annotated

import typer

from quancrypt_cli.api.messages import Language, text
from quancrypt_cli.facade.errors import CliError
from quancrypt_cli.facade.project_facade import ProjectFacade, ServiceLine

DEFAULT_TIMEOUT_S = 180

PathOption = Annotated[str, typer.Option("--path", help="Project root (default: the current directory)")]
TimeoutOption = Annotated[int, typer.Option("--timeout", min=1, max=1800, help="Seconds to wait for the services")]


def build_app(facade_factory: Callable[[], ProjectFacade], language: Language) -> typer.Typer:
    """The `quancrypt` app. The factory builds the facade when a command runs, so `--help` needs no installation."""
    app = typer.Typer(
        name="quancrypt",
        add_completion=False,
        no_args_is_help=True,
        # A traceback must never print local variables: the session token is one of them.
        pretty_exceptions_show_locals=False,
        help="Quancrypt: find RSA cryptography in a Spring Boot project and plan the move to ML-KEM/ML-DSA, locally.",
    )

    def say(key: str, **values: str) -> None:
        typer.echo(text(language, key, **values))

    def fail(error: CliError) -> typer.Exit:
        typer.echo(text(language, "error", text=text(language, error.code, detail=error.detail)), err=True)
        return typer.Exit(1)

    def show(services: tuple[ServiceLine, ...]) -> None:
        for service in services:
            state = text(language, "service.ok" if service.healthy else "service.bad")
            typer.echo(f"  {service.name:<18}{state}")

    @app.command("init")
    def init(path: PathOption = ".", timeout: TimeoutOption = DEFAULT_TIMEOUT_S) -> None:
        """Set Quancrypt up in a Maven or Gradle project root and show the web UI address."""
        say("starting")
        try:
            view = facade_factory().init(path, timeout)
        except CliError as error:
            raise fail(error) from None
        say("init.done", name=view.project_name, kind=view.kind)
        say("services")
        show(view.services)
        say("registered.new" if view.newly_registered else "registered.known")
        if view.token_renewed:
            say("token.renewed")
        if not view.token_protected:
            say("token.unprotected")
        say("ui.address", address=view.ui_address)
        if not view.gitignore_covers:
            say("gitignore.advice", line=view.gitignore_line)
        say("kvkk")

    @app.command("up")
    def up(path: PathOption = ".", timeout: TimeoutOption = DEFAULT_TIMEOUT_S) -> None:
        """Start the services of an initialised project."""
        say("starting")
        try:
            services = facade_factory().up(path, timeout)
        except CliError as error:
            raise fail(error) from None
        show(services)
        say("up.done")

    @app.command("down")
    def down() -> None:
        """Stop the services (the database volume is kept)."""
        try:
            facade_factory().down()
        except CliError as error:
            raise fail(error) from None
        say("down.done")

    @app.command("status")
    def status() -> None:
        """Show the health of the services; exit code 1 when a required one is not ready."""
        try:
            view = facade_factory().status()
        except CliError as error:
            raise fail(error) from None
        show(view.services)
        say("status.ok" if view.all_required_healthy else "status.bad")
        if not view.all_required_healthy:
            raise typer.Exit(1)

    @app.command("open")
    def open_ui(path: PathOption = ".") -> None:
        """Show the web UI address of an initialised project (no browser is started yet, D-279)."""
        try:
            view = facade_factory().open_ui(path)
        except CliError as error:
            raise fail(error) from None
        say("ui.address", address=view.address)

    return app
