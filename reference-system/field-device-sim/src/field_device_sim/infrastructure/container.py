"""Composition root: the only place that creates and wires the concrete classes."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from field_device_sim.facade.health_facade import HealthFacade
from field_device_sim.facade.terminal_facade import TerminalFacade
from field_device_sim.infrastructure.file_status_reporter import FileStatusReporter
from field_device_sim.infrastructure.paho_message_publisher import PahoMessagePublisher
from field_device_sim.infrastructure.settings import Settings
from field_device_sim.infrastructure.system_clock import SystemClock
from field_device_sim.infrastructure.system_random_source import SystemRandomSource
from field_device_sim.infrastructure.uuid_id_generator import UuidIdGenerator
from field_device_sim.usecase.check_health import CheckHealth
from field_device_sim.usecase.publish_transaction import PublishTransaction


@dataclass(frozen=True)
class Application:
    """The wired facade and the way to release its connection."""

    facade: TerminalFacade
    close: Callable[[], None]


def build_health_facade(settings: Settings) -> HealthFacade:
    """A facade for the health check only: it needs no broker connection and no certificate."""
    return HealthFacade(CheckHealth(SystemClock(), FileStatusReporter(settings.status_file)))


def build_application(settings: Settings, terminal_id: str, seed: int | None) -> Application:
    """Wire the simulator for one terminal and start connecting to the broker."""
    # Not security relevant: the generator only makes demo values reproducible.
    rng = random.Random(seed) if seed is not None else None  # noqa: S311
    status = FileStatusReporter(settings.status_file)
    publisher = PahoMessagePublisher(
        host=settings.broker_host,
        port=settings.broker_port,
        client_id=terminal_id,
        ca_file=settings.ca_file,
        certificate_file=settings.certificate_file(terminal_id),
        key_file=settings.key_file(terminal_id),
    )
    publisher.start()
    publish = PublishTransaction(
        publisher=publisher,
        clock=SystemClock(),
        ids=UuidIdGenerator(rng),
        random=SystemRandomSource(rng),
        status=status,
    )
    return Application(TerminalFacade(publish), publisher.close)
