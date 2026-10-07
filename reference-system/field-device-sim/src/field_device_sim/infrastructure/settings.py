"""Configuration from environment variables; the defaults are for local development only."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_BROKER_URL = "ssl://localhost:8883"
DEFAULT_CERTS_DIR = "../certs/out"
DEFAULT_STATUS_FILE = str(Path(tempfile.gettempdir()) / "field-device-sim.status")


class SettingsError(ValueError):
    """A setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Where the broker is, where the TLS files are and where the health status is kept."""

    broker_host: str
    broker_port: int
    certs_dir: Path
    status_file: Path

    @staticmethod
    def from_env(environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        broker_url = env.get("MQTT_BROKER_URL", DEFAULT_BROKER_URL)
        parts = urlsplit(broker_url)
        if parts.scheme != "ssl" or not parts.hostname:
            raise SettingsError("MQTT_BROKER_URL must look like ssl://host:port (TLS only)")
        return Settings(
            broker_host=parts.hostname,
            broker_port=parts.port or 8883,
            certs_dir=Path(env.get("QBANK_CERTS_DIR", DEFAULT_CERTS_DIR)),
            status_file=Path(env.get("FIELD_DEVICE_SIM_STATUS_FILE", DEFAULT_STATUS_FILE)),
        )

    @property
    def ca_file(self) -> Path:
        return self.certs_dir / "ca.crt.pem"

    def certificate_file(self, terminal_id: str) -> Path:
        """The client certificate of a terminal: <certs dir>/<terminal id>.crt.pem."""
        return self.certs_dir / f"{terminal_id}.crt.pem"

    def key_file(self, terminal_id: str) -> Path:
        """The private key of a terminal: <certs dir>/<terminal id>.key.pem."""
        return self.certs_dir / f"{terminal_id}.key.pem"
