"""ComposeRunner adapter: the `docker compose` CLI as a child process.

The arguments are a fixed list and no shell is involved (`shell` stays False, D-277). The session token travels only in
the environment of the child process: never on the command line, never in a log line, never in an error message.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from quancrypt_cli.domain.session_token import SessionToken
from quancrypt_cli.port.outbound.errors import ComposeError

LOG = logging.getLogger("quancrypt_cli.compose")
PROFILE = "app"
_DOWN_TIMEOUT_S = 120
# `--wait-timeout` is the time for the containers to become healthy. The first `up` also builds the images (Gradle, uv),
# which takes minutes and is not covered by it, so the process gets a generous margin on top.
_BUILD_MARGIN_S = 1800
_ERROR_LINES = 5
_ERROR_CHARS = 600


class DockerComposeRunner:
    """Implements ComposeRunner for the Quancrypt installation in `home` (docker-compose.yml and .env)."""

    def __init__(
        self,
        home: Path,
        executable: str = "docker",
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._home = home
        self._executable = executable
        self._run = run

    def up(self, project_root: Path, token: SessionToken, wait_timeout_s: int) -> None:
        environment = {**os.environ, "PROJECT_ROOT": str(project_root), "QUANCRYPT_SESSION_TOKEN": token.value}
        self._compose(
            ["up", "-d", "--wait", "--wait-timeout", str(wait_timeout_s)],
            environment,
            timeout_s=wait_timeout_s + _BUILD_MARGIN_S,
            secrets=(token.value,),
        )

    def down(self) -> None:
        self._compose(["down"], dict(os.environ), timeout_s=_DOWN_TIMEOUT_S, secrets=())

    def _compose(
        self, command: Sequence[str], environment: Mapping[str, str], timeout_s: int, secrets: Sequence[str]
    ) -> None:
        arguments = [
            self._executable,
            "compose",
            "--project-directory",
            str(self._home),
            "--env-file",
            str(self._home / ".env"),
            "-f",
            str(self._home / "docker-compose.yml"),
            "--profile",
            PROFILE,
            *command,
        ]
        LOG.debug("docker compose %s", command[0])
        try:
            completed = self._run(
                arguments,
                env=dict(environment),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            raise ComposeError("the docker command was not found; is Docker installed and running?") from None
        except subprocess.TimeoutExpired:
            raise ComposeError(f"docker compose {command[0]} did not finish in {timeout_s} s") from None
        except OSError:
            raise ComposeError("docker compose could not be started") from None
        if completed.returncode != 0:
            raise ComposeError(
                f"docker compose {command[0]} exited with code {completed.returncode}: "
                + _tail(completed.stderr, secrets)
            )


def _tail(stderr: str, secrets: Sequence[str]) -> str:
    """The last lines of the error output, with every known secret blanked and the length limited."""
    text = "\n".join((stderr or "").strip().splitlines()[-_ERROR_LINES:])
    for secret in secrets:
        text = text.replace(secret, "***")
    return text[-_ERROR_CHARS:] or "no error output"
