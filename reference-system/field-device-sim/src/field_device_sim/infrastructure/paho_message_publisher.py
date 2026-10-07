"""MQTT adapter: publishes transactions over TLS with a client certificate (mutual TLS)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from field_device_sim.domain.terminal_transaction import TerminalTransaction
from field_device_sim.port.outbound.message_publisher import PublishError

LOG = logging.getLogger("field_device_sim.mqtt")

_QOS = 1
_KEEPALIVE_SECONDS = 30


def topic_for(terminal_id: str) -> str:
    """The topic a terminal publishes to (contracts/terminal-transaction.schema.json)."""
    return f"terminal/{terminal_id}/transactions"


def payload_for(transaction: TerminalTransaction) -> bytes:
    """The JSON message of a transaction: exactly the fields of the contract, compact."""
    message = {
        "transactionId": transaction.transaction_id,
        "terminalId": transaction.terminal_id,
        "accountId": transaction.account_id,
        "amount": f"{transaction.amount:.2f}",
        "currency": transaction.currency,
        "occurredAt": transaction.occurred_at.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    return json.dumps(message, separators=(",", ":")).encode("utf-8")


class PahoMessagePublisher:
    """Implements MessagePublisher with paho-mqtt (MQTT 3.1.1, QoS 1).

    The connection is made in the background and re-established automatically. A message is sent only while the
    connection is up; otherwise publish() fails at once instead of queueing, so that no stale transaction is
    delivered later. A message that was sent but not acknowledged in time is retransmitted by the MQTT client after a
    reconnect; the payment service ignores a repeated transactionId.
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_id: str,
        ca_file: Path,
        certificate_file: Path,
        key_file: Path,
        acknowledgement_timeout_seconds: float = 5.0,
    ) -> None:
        self._host = host
        self._port = port
        self._acknowledgement_timeout = acknowledgement_timeout_seconds
        self._connected = threading.Event()
        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        # Mutual TLS: the broker certificate and its host name are verified against the demo CA (paho's default
        # keeps host name verification on), and the client presents its own certificate.
        self._client.tls_set(
            ca_certs=str(ca_file),
            certfile=str(certificate_file),
            keyfile=str(key_file),
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_connect_fail = self._on_connect_fail

    def start(self) -> None:
        """Start connecting in the background; returns at once."""
        self._client.connect_async(self._host, self._port, keepalive=_KEEPALIVE_SECONDS)
        self._client.loop_start()

    def wait_until_connected(self, timeout_seconds: float) -> bool:
        """Wait for the connection to be up; False when it is not up in time."""
        return self._connected.wait(timeout_seconds)

    def close(self) -> None:
        """Disconnect and stop the background thread."""
        self._client.disconnect()
        self._client.loop_stop()

    def publish(self, transaction: TerminalTransaction) -> None:
        if not self._client.is_connected():
            raise PublishError("not connected to the broker")
        info = self._client.publish(topic_for(transaction.terminal_id), payload_for(transaction), qos=_QOS)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise PublishError(f"the message could not be sent (code {info.rc})")
        try:
            info.wait_for_publish(timeout=self._acknowledgement_timeout)
        except (ValueError, RuntimeError) as error:
            raise PublishError("the message could not be sent") from error
        if not info.is_published():
            raise PublishError("the broker did not acknowledge the message in time")

    def _on_connect(self, _client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        if reason_code == 0:
            self._connected.set()
            LOG.info("connected to the broker")
        else:
            LOG.warning("the broker refused the connection: %s", reason_code)

    def _on_disconnect(self, _client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        self._connected.clear()
        LOG.warning("disconnected from the broker: %s", reason_code)

    def _on_connect_fail(self, _client: Any, _userdata: Any) -> None:
        LOG.warning("connecting to the broker failed; retrying")
