"""One-off Superset set-up step (P7.5, D-343d): the admin user from .env. Run by the `superset-init` compose service after
`superset db upgrade` and `superset init` (the image's own commands).

The password comes from SUPERSET_ADMIN_PASSWORD and is never printed or passed on a command line. An existing user is
left as it is (its password is changed in the UI or by deleting the `superset-home` volume)."""

from __future__ import annotations

import os
import re
import sys

_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_MIN_PASSWORD_CHARS = 12


def _settings() -> tuple[str, str]:
    name = os.environ.get("SUPERSET_ADMIN_USER", "admin")
    password = os.environ.get("SUPERSET_ADMIN_PASSWORD", "")
    if not _NAME.fullmatch(name):
        sys.exit("SUPERSET_ADMIN_USER must be 1-64 letters, digits, '.', '_' or '-'")
    if len(password) < _MIN_PASSWORD_CHARS or "CHANGE_ME" in password:
        sys.exit(f"SUPERSET_ADMIN_PASSWORD must be set in .env: at least {_MIN_PASSWORD_CHARS} characters, no CHANGE_ME")
    return name, password


def main() -> None:
    name, password = _settings()
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import security_manager

        if security_manager.find_user(username=name) is not None:
            print(f"Superset admin user '{name}' already exists; left unchanged")
            return
        role = security_manager.find_role("Admin")
        if role is None:
            sys.exit("the Admin role is missing: run `superset init` first")
        user = security_manager.add_user(name, "Quancrypt", "Admin", f"{name}@quancrypt.local", role, password=password)
        if not user:
            sys.exit(f"could not create the Superset admin user '{name}'")
        print(f"Superset admin user '{name}' created")


if __name__ == "__main__":
    main()
