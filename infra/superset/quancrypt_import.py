"""`make superset-import` (P7.5, D-344i): loads the versioned dashboard bundle in data-platform/superset/ (mounted read-only
at /bundle) into Superset with the image's own v1 importer (`ImportDashboardsCommand`, as `superset import-dashboards`).

The bundle's database file carries the warehouse connection with a masked password; the password of the read-only
`warehouse_reader` role is handed to the importer from WAREHOUSE_READER_PASSWORD and is never written to the bundle.
Charts and datasets that already exist (same uuid) are kept as they are by the importer; dashboards are overwritten."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BUNDLE = Path(os.environ.get("QUANCRYPT_SUPERSET_BUNDLE", "/bundle"))
DATABASE_FILE = "databases/Quancrypt_Warehouse.yaml"
_PARTS = ("metadata.yaml", "databases/", "datasets/", "charts/", "dashboards/")


def contents(bundle: Path) -> dict[str, str]:
    """Every YAML file of the bundle by its path inside the bundle (the importer's keys)."""
    files: dict[str, str] = {}
    for path in sorted(bundle.rglob("*.yaml")):
        name = path.relative_to(bundle).as_posix()
        if name.startswith(_PARTS):
            files[name] = path.read_text(encoding="utf-8")
    if "metadata.yaml" not in files or DATABASE_FILE not in files:
        sys.exit(f"{bundle} is not the Quancrypt dashboard bundle (metadata.yaml or {DATABASE_FILE} missing)")
    return files


def main() -> None:
    password = os.environ.get("WAREHOUSE_READER_PASSWORD", "")
    if not password or "CHANGE_ME" in password:
        sys.exit("WAREHOUSE_READER_PASSWORD must be set in .env")
    owner = os.environ.get("SUPERSET_ADMIN_USER", "admin")
    files = contents(BUNDLE)

    from flask import g
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import security_manager
        from superset.commands.dashboard.importers.dispatcher import ImportDashboardsCommand

        user = security_manager.find_user(username=owner)
        if user is None:
            sys.exit(f"Superset user '{owner}' not found: the superset-init service creates it")
        g.user = user
        ImportDashboardsCommand(files, overwrite=True, passwords={DATABASE_FILE: password}).run()
    dashboards = sum(1 for name in files if name.startswith("dashboards/"))
    charts = sum(1 for name in files if name.startswith("charts/"))
    print(f"imported {dashboards} dashboards and {charts} charts")


if __name__ == "__main__":
    main()
