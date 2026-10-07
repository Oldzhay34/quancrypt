"""Plain paho clients that stand in for the other parties of the broker in the tests."""

from __future__ import annotations

import json
import threading
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from support.mosquitto import MosquittoBroker, certs_dir


class ProbeClient:
    """A connected (or failing) MQTT client with a certificate identity, collecting what it receives."""

    def __init__(self, broker: MosquittoBroker, identity: str | None, client_id: str) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []
        self.subscribe_failed: bool | None = None
        self._connected = threading.Event()
        self._subscribed = threading.Event()
        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv311
        )
        certs = certs_dir()
        if identity is None:
            self._client.tls_set(ca_certs=str(certs / "ca.crt.pem"))
        else:
            self._client.tls_set(
                ca_certs=str(certs / "ca.crt.pem"),
                certfile=str(certs / f"{identity}.crt.pem"),
                keyfile=str(certs / f"{identity}.key.pem"),
            )
        self._client.on_connect = self._on_connect
        self._client.on_subscribe = self._on_subscribe
        self._client.on_message = self._on_message
        self._client.connect_async(broker.host, broker.port, keepalive=30)
        self._client.loop_start()

    def _on_connect(self, _client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        if reason_code == 0:
            self._connected.set()

    def _on_subscribe(self, _client: Any, _userdata: Any, _mid: Any, reason_codes: Any, _properties: Any) -> None:
        self.subscribe_failed = any(code.is_failure for code in reason_codes)
        self._subscribed.set()

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        self.messages.append((message.topic, json.loads(message.payload)))

    def wait_connected(self, timeout: float = 10) -> bool:
        return self._connected.wait(timeout)

    def subscribe(self, topic: str, timeout: float = 10) -> bool:
        """Subscribe; True when the broker granted the subscription, False when it refused it."""
        self._client.subscribe(topic, qos=1)
        if not self._subscribed.wait(timeout):
            raise TimeoutError("no SUBACK")
        return not bool(self.subscribe_failed)

    def publish(self, topic: str, payload: dict[str, Any], timeout: float = 10) -> None:
        info = self._client.publish(topic, json.dumps(payload), qos=1)
        info.wait_for_publish(timeout)

    def close(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()
