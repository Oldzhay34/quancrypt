"""Command line of the simulator.

python -m field_device_sim run --terminal-id terminal-001 --interval 5
python -m field_device_sim healthcheck [--max-age 30]
"""

from __future__ import annotations

import argparse
import logging
import re
import signal
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import FrameType

from field_device_sim.facade.errors import PublishFailedError
from field_device_sim.facade.health_facade import HealthFacade
from field_device_sim.facade.terminal_facade import TerminalFacade

LOG = logging.getLogger("field_device_sim.cli")

DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_MAX_AGE_SECONDS = 30.0


@dataclass(frozen=True)
class RunningApplication:
    """A wired publishing facade and the way to release its connection."""

    facade: TerminalFacade
    close: Callable[[], None]


# The composition root (outside the layers) hands these factories in, so that the CLI never imports infrastructure.
ApplicationFactory = Callable[[str, int | None], RunningApplication]
HealthFacadeFactory = Callable[[], HealthFacade]


_TERMINAL_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def _terminal_id(text: str) -> str:
    # The id names certificate files and the MQTT topic, so it is checked before anything is built from it.
    if not _TERMINAL_ID.fullmatch(text):
        raise argparse.ArgumentTypeError("must be 1 to 64 characters from A-Z a-z 0-9 . _ -")
    return text


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not a number: {text}") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="field_device_sim", description="QBank field terminal simulator")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="publish a test transaction at a fixed interval until stopped")
    run.add_argument(
        "--terminal-id",
        type=_terminal_id,
        required=True,
        help="terminal identity; also the name of its certificate files",
    )
    run.add_argument(
        "--interval", type=_positive_float, default=DEFAULT_INTERVAL_SECONDS, help="seconds between transactions"
    )
    run.add_argument("--seed", type=int, default=None, help="seed for reproducible accounts, amounts and ids")

    health = commands.add_parser("healthcheck", help="exit 0 when a transaction was published recently, 1 otherwise")
    health.add_argument(
        "--max-age",
        type=_positive_float,
        default=DEFAULT_MAX_AGE_SECONDS,
        help="longest accepted seconds since the last publication",
    )
    return parser


def run_loop(facade: TerminalFacade, terminal_id: str, interval_seconds: float, stop: threading.Event) -> None:
    """Publish one transaction per interval until stop is set; a failed publication is logged and retried later."""
    while not stop.is_set():
        try:
            view = facade.publish_next(terminal_id)
            # Only the id is logged: account and amount are payment data, which the payment service does not log either.
            LOG.info("published transaction %s", view.transaction_id)
        except PublishFailedError as error:
            LOG.warning("publishing failed: %s", error)
        stop.wait(interval_seconds)


def main(
    argv: Sequence[str],
    application_factory: ApplicationFactory,
    health_facade_factory: HealthFacadeFactory,
) -> int:
    """Run the command line; returns the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "healthcheck":
        health = health_facade_factory().health(args.max_age)
        LOG.info("%s: %s", "healthy" if health.healthy else "unhealthy", health.reason)
        return 0 if health.healthy else 1

    stop = threading.Event()

    def request_stop(_signal_number: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    application = application_factory(args.terminal_id, args.seed)
    LOG.info("terminal %s started, interval %s s", args.terminal_id, args.interval)
    try:
        run_loop(application.facade, args.terminal_id, args.interval, stop)
    finally:
        application.close()
    LOG.info("terminal %s stopped", args.terminal_id)
    return 0
