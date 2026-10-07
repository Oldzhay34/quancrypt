from __future__ import annotations

import json
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from field_device_sim.domain.terminal_transaction import TerminalTransaction
from field_device_sim.infrastructure.file_status_reporter import FileStatusReporter
from field_device_sim.infrastructure.json_logging import JsonFormatter
from field_device_sim.infrastructure.paho_message_publisher import payload_for, topic_for
from field_device_sim.infrastructure.settings import Settings, SettingsError
from field_device_sim.infrastructure.system_clock import SystemClock
from field_device_sim.infrastructure.system_random_source import SystemRandomSource
from field_device_sim.infrastructure.uuid_id_generator import UuidIdGenerator

MOMENT = datetime(2026, 10, 7, 10, 15, 30, tzinfo=timezone.utc)


def test_the_system_clock_is_timezone_aware_utc() -> None:
    now = SystemClock().now()

    assert now.utcoffset() == timedelta(0)
    assert abs((datetime.now(timezone.utc) - now).total_seconds()) < 5


def test_unseeded_ids_are_valid_version_4_uuids_and_differ() -> None:
    generator = UuidIdGenerator()

    first, second = generator.new_id(), generator.new_id()

    assert first != second
    assert str(uuid.UUID(first, version=4)) == first
    assert uuid.UUID(first).version == 4


def test_seeded_ids_and_random_values_are_reproducible() -> None:
    def sample(seed: int) -> tuple[list[str], list[str], list[int]]:
        rng = random.Random(seed)
        ids = UuidIdGenerator(rng)
        source = SystemRandomSource(rng)
        return (
            [ids.new_id() for _ in range(3)],
            [source.pick(("a", "b", "c")) for _ in range(5)],
            [source.integer(100, 50_000) for _ in range(5)],
        )

    assert sample(7) == sample(7)
    assert sample(7) != sample(8)
    assert all(uuid.UUID(identifier).version == 4 for identifier in sample(7)[0])


def test_random_values_stay_in_range() -> None:
    source = SystemRandomSource()

    values = [source.integer(100, 105) for _ in range(200)]

    assert min(values) >= 100
    assert max(values) <= 105
    assert {source.pick(("x", "y")) for _ in range(50)} == {"x", "y"}


def test_the_status_file_remembers_the_last_success(tmp_path: Path) -> None:
    reporter = FileStatusReporter(tmp_path / "status")
    assert reporter.last_success() is None

    reporter.record_success(MOMENT)
    assert reporter.last_success() == MOMENT

    later = MOMENT + timedelta(seconds=5)
    reporter.record_success(later)
    assert reporter.last_success() == later
    assert [p.name for p in tmp_path.iterdir()] == ["status"], "no temporary file may be left behind"


@pytest.mark.parametrize("content", ["", "garbage", "2026-10-07T10:15:30"])
def test_an_unreadable_status_file_means_no_success(tmp_path: Path, content: str) -> None:
    path = tmp_path / "status"
    path.write_text(content, encoding="utf-8")

    assert FileStatusReporter(path).last_success() is None


def test_the_topic_and_payload_follow_the_contract() -> None:
    transaction = TerminalTransaction(
        transaction_id="00000000-0000-4000-8000-000000000001",
        terminal_id="terminal-001",
        account_id="acc-001",
        amount=Decimal("12.50"),
        currency="TRY",
        occurred_at=MOMENT + timedelta(microseconds=123456),
    )

    assert topic_for("terminal-001") == "terminal/terminal-001/transactions"
    payload = payload_for(transaction)
    assert payload == (
        b'{"transactionId":"00000000-0000-4000-8000-000000000001","terminalId":"terminal-001",'
        b'"accountId":"acc-001","amount":"12.50","currency":"TRY","occurredAt":"2026-10-07T10:15:30Z"}'
    )
    assert list(json.loads(payload)) == ["transactionId", "terminalId", "accountId", "amount", "currency", "occurredAt"]


def test_settings_default_to_local_development() -> None:
    settings = Settings.from_env({})

    assert (settings.broker_host, settings.broker_port) == ("localhost", 8883)
    assert settings.ca_file == Path("../certs/out/ca.crt.pem")
    assert settings.certificate_file("terminal-001") == Path("../certs/out/terminal-001.crt.pem")
    assert settings.key_file("terminal-001") == Path("../certs/out/terminal-001.key.pem")


def test_settings_come_from_the_environment() -> None:
    settings = Settings.from_env(
        {
            "MQTT_BROKER_URL": "ssl://mosquitto:8883",
            "QBANK_CERTS_DIR": "/certs",
            "FIELD_DEVICE_SIM_STATUS_FILE": "/tmp/status",
        }
    )

    assert (settings.broker_host, settings.broker_port) == ("mosquitto", 8883)
    assert settings.certs_dir == Path("/certs")
    assert settings.status_file == Path("/tmp/status")


@pytest.mark.parametrize("url", ["tcp://mosquitto:1883", "mqtt://mosquitto", "mosquitto:8883", "ssl://"])
def test_a_broker_url_without_tls_is_refused(url: str) -> None:
    with pytest.raises(SettingsError):
        Settings.from_env({"MQTT_BROKER_URL": url})


def test_log_lines_are_json_with_the_required_fields() -> None:
    record = logging.LogRecord("x", logging.WARNING, __file__, 1, 'say "hi"\n%s', ("there",), None)

    line = JsonFormatter().format(record)

    parsed = json.loads(line)
    assert list(parsed) == ["timestamp", "level", "service", "traceId", "message"]
    assert parsed["level"] == "WARNING"
    assert parsed["service"] == "field-device-sim"
    assert parsed["traceId"] is None
    assert parsed["message"] == 'say "hi"\nthere'
    assert "\n" not in line


def test_a_logged_exception_contributes_only_its_class_name() -> None:
    try:
        raise ValueError("secret detail")
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())

    line = JsonFormatter().format(record)

    assert "ValueError" in line
    assert "secret detail" not in line
