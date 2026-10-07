"""Entry point and composition: wires the CLI to the infrastructure (python -m field_device_sim)."""

from __future__ import annotations

import sys

from field_device_sim.api.cli import RunningApplication, main
from field_device_sim.facade.health_facade import HealthFacade
from field_device_sim.infrastructure.container import build_application, build_health_facade
from field_device_sim.infrastructure.json_logging import configure_logging
from field_device_sim.infrastructure.settings import Settings


def _application(terminal_id: str, seed: int | None) -> RunningApplication:
    application = build_application(Settings.from_env(), terminal_id, seed)
    return RunningApplication(application.facade, application.close)


def _health_facade() -> HealthFacade:
    return build_health_facade(Settings.from_env())


if __name__ == "__main__":
    configure_logging()
    sys.exit(main(sys.argv[1:], _application, _health_facade))
