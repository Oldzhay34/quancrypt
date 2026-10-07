"""A real Mosquitto 2.0.22 broker for the integration and contract tests.

The container is created with the docker CLI, gets the real configuration, ACL and only the three certificate files
the broker needs (never the CA key) copied in, and is removed afterwards. Without Docker the tests fail; they are not
skipped.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

IMAGE = "eclipse-mosquitto:2.0.22"
BROKER_FILES = ("ca.crt.pem", "mosquitto.crt.pem", "mosquitto.key.pem")


def certs_dir() -> Path:
    configured = os.environ.get("QBANK_CERTS_DIR")
    path = Path(configured) if configured else Path(__file__).resolve().parents[3] / "certs" / "out"
    if not (path / "ca.crt.pem").is_file():
        raise RuntimeError(f"certificates not found in {path}; run `make certs` (reference-system/certs/generate.sh)")
    return path


def mosquitto_dir() -> Path:
    configured = os.environ.get("QBANK_MOSQUITTO_DIR")
    path = Path(configured) if configured else Path(__file__).resolve().parents[3] / "mosquitto"
    if not (path / "mosquitto.conf").is_file():
        raise RuntimeError(f"mosquitto.conf not found in {path}")
    return path


def _docker(*arguments: str) -> str:
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(arguments[:2])} failed: {result.stderr.strip()}")
    return result.stdout.strip()


class MosquittoBroker:
    """Starts and stops the broker container."""

    def __init__(self) -> None:
        self._name = f"fds-test-mosquitto-{uuid.uuid4().hex[:8]}"
        self.host = "localhost"
        self.port = 0

    def start(self) -> None:
        _docker("create", "--name", self._name, "-p", "127.0.0.1::8883", IMAGE)
        try:
            _docker("cp", str(mosquitto_dir() / "mosquitto.conf"), f"{self._name}:/mosquitto/config/mosquitto.conf")
            _docker("cp", str(mosquitto_dir() / "acl"), f"{self._name}:/mosquitto/config/acl")
            staging = Path(tempfile.mkdtemp(prefix="fds-broker-certs-"))
            try:
                staging.chmod(0o700)
                for name in BROKER_FILES:
                    shutil.copy(certs_dir() / name, staging / name)
                    (staging / name).chmod(0o600)
                _docker("cp", str(staging), f"{self._name}:/mosquitto/certs")
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            _docker("start", self._name)
            self._wait_until_running()
            mapping = _docker("port", self._name, "8883/tcp").splitlines()[0]
            self.port = int(mapping.rsplit(":", 1)[1])
        except Exception:
            self.stop()
            raise

    def _wait_until_running(self) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            logs = _docker("logs", self._name)
            if "running" in logs:
                return
            state = _docker("inspect", "-f", "{{.State.Running}}", self._name)
            if state != "true":
                raise RuntimeError(f"the broker stopped at startup: {logs}")
            time.sleep(0.3)
        raise RuntimeError("the broker did not start in time")

    def logs(self) -> str:
        return _docker("logs", self._name)

    def stop(self) -> None:
        subprocess.run(["docker", "rm", "-f", self._name], capture_output=True, timeout=60, check=False)
