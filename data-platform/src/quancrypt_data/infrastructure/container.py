"""The composition root (hexagonal-service section 2): the only module that sees every layer. It reads the settings,
builds the adapters, the use cases and the facade, and hands them to the HTTP application."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from quancrypt_data.api.app import create_app
from quancrypt_data.facade.ingest_facade import IngestFacade
from quancrypt_data.infrastructure.logging_setup import configure_logging
from quancrypt_data.infrastructure.persistence.database import Database, DatabaseReadiness
from quancrypt_data.infrastructure.persistence.repositories import (
    PostgresBatchStore,
    PostgresErasureAudit,
    PostgresEventStore,
    PostgresProjectDataEraser,
    PostgresProjectKeyLock,
    PostgresQuarantineStore,
    StaticProjectKeyTableRegistry,
)
from quancrypt_data.infrastructure.schema.json_schema_catalog import JsonSchemaCatalog
from quancrypt_data.infrastructure.settings import Settings, load_settings
from quancrypt_data.infrastructure.system import RandomIdGenerator, SystemClock
from quancrypt_data.usecase.classification import EventClassifier
from quancrypt_data.usecase.delete_project_data_service import DeleteProjectDataService
from quancrypt_data.usecase.ingest_events_service import IngestEventsService


@dataclass(frozen=True)
class Container:
    settings: Settings
    database: Database
    facade: IngestFacade
    delete_project_data: DeleteProjectDataService
    ingest_events: IngestEventsService


def build_container(settings: Settings) -> Container:
    database = Database(settings.database)
    clock = SystemClock()
    ids = RandomIdGenerator()
    locks = PostgresProjectKeyLock(database)
    registry = StaticProjectKeyTableRegistry()
    audit = PostgresErasureAudit(database)
    delete_project_data = DeleteProjectDataService(
        transactions=database,
        registry=registry,
        eraser=PostgresProjectDataEraser(database, registry),
        audit=audit,
        locks=locks,
        clock=clock,
        ids=ids,
    )
    ingest_events = IngestEventsService(
        transactions=database,
        classifier=EventClassifier(JsonSchemaCatalog(settings.schemas_dir)),
        events=PostgresEventStore(database),
        quarantine=PostgresQuarantineStore(database),
        batches=PostgresBatchStore(database),
        locks=locks,
        audit=audit,
        delete_project_data=delete_project_data,
        clock=clock,
        ids=ids,
    )
    return Container(
        settings=settings,
        database=database,
        facade=IngestFacade(ingest_events),
        delete_project_data=delete_project_data,
        ingest_events=ingest_events,
    )


def build_application(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    container = build_container(settings)
    return create_app(
        container.facade,
        token=settings.internal_token,
        checks=[DatabaseReadiness(container.database)],
        on_startup=lambda: container.database.migrate(settings.migrations_dir),
        on_shutdown=container.database.close,
    )
