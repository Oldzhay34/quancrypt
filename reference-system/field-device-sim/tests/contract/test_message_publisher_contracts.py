"""The MessagePublisher contract against the fake and against the real MQTT adapter on a real Mosquitto broker."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

import pytest

from contract.message_publisher_contract import MessagePublisherContract
from field_device_sim.domain.terminal_transaction import TerminalTransaction
from field_device_sim.infrastructure.paho_message_publisher import PahoMessagePublisher
from field_device_sim.port.outbound.message_publisher import MessagePublisher
from support.fakes import FakeMessagePublisher
from support.mosquitto import MosquittoBroker, certs_dir
from support.mqtt_clients import ProbeClient


class TestFakeMessagePublisher(MessagePublisherContract):
    @pytest.fixture(autouse=True)
    def _wire(self) -> None:
        self._fake = FakeMessagePublisher()

    def publisher(self) -> MessagePublisher:
        return self._fake

    def unavailable_publisher(self) -> MessagePublisher:
        return FakeMessagePublisher(failing=True)

    def delivered(self) -> list[TerminalTransaction]:
        return list(self._fake.published)


class TestPahoMessagePublisher(MessagePublisherContract):
    """The adapter publishes as terminal-001; the payment service identity listens on terminal/+/transactions."""

    @pytest.fixture(autouse=True)
    def _wire(self, broker: MosquittoBroker) -> Iterator[None]:
        self._broker = broker
        self._publishers: list[PahoMessagePublisher] = []
        self._listener = ProbeClient(broker, "payment-to-mosquitto", "contract-listener")
        assert self._listener.wait_connected()
        assert self._listener.subscribe("terminal/+/transactions")
        yield
        self._listener.close()
        for publisher in self._publishers:
            publisher.close()

    def _new(self, port: int) -> PahoMessagePublisher:
        certs = certs_dir()
        publisher = PahoMessagePublisher(
            host=self._broker.host,
            port=port,
            client_id="terminal-001",
            ca_file=certs / "ca.crt.pem",
            certificate_file=certs / "terminal-001.crt.pem",
            key_file=certs / "terminal-001.key.pem",
            acknowledgement_timeout_seconds=5,
        )
        publisher.start()
        self._publishers.append(publisher)
        return publisher

    def publisher(self) -> MessagePublisher:
        publisher = self._new(self._broker.port)
        assert publisher.wait_until_connected(10), "the adapter must reach the broker with its client certificate"
        return publisher

    def unavailable_publisher(self) -> MessagePublisher:
        return self._new(1)  # nothing listens on port 1

    def delivered(self) -> list[TerminalTransaction]:
        return [
            TerminalTransaction(
                transaction_id=message["transactionId"],
                terminal_id=message["terminalId"],
                account_id=message["accountId"],
                amount=Decimal(message["amount"]),
                currency=message["currency"],
                occurred_at=datetime.fromisoformat(message["occurredAt"].replace("Z", "+00:00")),
            )
            for _topic, message in list(self._listener.messages)
        ]
