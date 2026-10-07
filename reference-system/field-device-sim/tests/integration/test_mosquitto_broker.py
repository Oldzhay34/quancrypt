"""The real broker configuration (mosquitto.conf and acl) with real certificates: who may connect, publish and read."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from support.mosquitto import MosquittoBroker
from support.mqtt_clients import ProbeClient

MESSAGE = {
    "transactionId": "00000000-0000-4000-8000-000000000001",
    "terminalId": "terminal-001",
    "accountId": "acc-001",
    "amount": "12.50",
    "currency": "TRY",
    "occurredAt": "2026-10-07T10:15:30Z",
}


@pytest.fixture
def payment(broker: MosquittoBroker) -> Iterator[ProbeClient]:
    client = ProbeClient(broker, "payment-to-mosquitto", "it-payment")
    assert client.wait_connected()
    assert client.subscribe("terminal/+/transactions")
    yield client
    client.close()


@pytest.fixture
def terminal(broker: MosquittoBroker) -> Iterator[ProbeClient]:
    client = ProbeClient(broker, "terminal-001", "it-terminal-001")
    assert client.wait_connected()
    yield client
    client.close()


def _wait_for(client: ProbeClient, count: int, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(client.messages) < count:
        time.sleep(0.05)


def test_a_terminal_publishes_to_its_own_topic_and_the_payment_identity_receives_it(
    payment: ProbeClient, terminal: ProbeClient
) -> None:
    terminal.publish("terminal/terminal-001/transactions", MESSAGE)

    _wait_for(payment, 1)
    assert payment.messages == [("terminal/terminal-001/transactions", MESSAGE)]


def test_a_terminal_cannot_publish_to_the_topic_of_another_terminal(
    payment: ProbeClient, terminal: ProbeClient
) -> None:
    forged = {**MESSAGE, "terminalId": "terminal-002"}

    terminal.publish("terminal/terminal-002/transactions", forged)  # the broker acknowledges but drops it
    terminal.publish("terminal/terminal-001/transactions", MESSAGE)  # a control message behind it

    _wait_for(payment, 1)
    time.sleep(1)
    assert payment.messages == [("terminal/terminal-001/transactions", MESSAGE)]


def test_a_terminal_cannot_read_anything(payment: ProbeClient, terminal: ProbeClient) -> None:
    # Mosquitto answers a subscription of MQTT 3.1.1 clients with success but never delivers what the ACL forbids.
    terminal.subscribe("terminal/+/transactions")

    terminal.publish("terminal/terminal-001/transactions", MESSAGE)

    _wait_for(payment, 1)  # the message did get through to the one identity that may read it
    time.sleep(1)
    assert len(payment.messages) == 1
    assert terminal.messages == []


def test_a_valid_certificate_that_the_acl_does_not_know_can_connect_but_neither_read_nor_write_terminal_topics(
    broker: MosquittoBroker, payment: ProbeClient
) -> None:
    stranger = ProbeClient(broker, "payment-to-account", "it-stranger")
    try:
        assert stranger.wait_connected()
        stranger.subscribe("terminal/+/transactions")
        stranger.publish("terminal/terminal-001/transactions", MESSAGE)  # dropped: it may not write
        time.sleep(1)
        assert payment.messages == []

        terminal = ProbeClient(broker, "terminal-001", "it-terminal-for-stranger")
        try:
            assert terminal.wait_connected()
            terminal.publish("terminal/terminal-001/transactions", MESSAGE)
            _wait_for(payment, 1)
            time.sleep(1)
        finally:
            terminal.close()
        assert len(payment.messages) == 1
        assert stranger.messages == []
    finally:
        stranger.close()


def test_any_ca_signed_identity_can_publish_below_its_own_common_name_known_weakness(
    broker: MosquittoBroker, payment: ProbeClient
) -> None:
    # Known weakness (D-108, D-118, ILERIDE): `pattern write terminal/%u/transactions` applies to every identity
    # the demo CA signed, not only to terminals. The payment service would record such a message.
    stranger = ProbeClient(broker, "payment-to-account", "it-stranger-own-topic")
    try:
        assert stranger.wait_connected()
        stranger.publish("terminal/payment-to-account/transactions", {**MESSAGE, "terminalId": "payment-to-account"})
        _wait_for(payment, 1)
    finally:
        stranger.close()
    assert [topic for topic, _ in payment.messages] == ["terminal/payment-to-account/transactions"]


def test_a_client_without_a_certificate_is_not_let_in(broker: MosquittoBroker) -> None:
    anonymous = ProbeClient(broker, None, "it-anonymous")
    try:
        assert anonymous.wait_connected(timeout=4) is False
    finally:
        anonymous.close()


def test_the_broker_started_with_the_real_configuration(broker: MosquittoBroker) -> None:
    logs = broker.logs()

    assert "Opening ipv4 listen socket on port 8883" in logs
    assert "Error: " not in logs, "a configuration or startup error would be logged as 'Error: ...'"
