"""Zentrale Synchronisierung und Protokollierung einer Fahrt.

MQTT-Abonnements, Ereignislogik, Ringpuffer und Dateiausgabe werden in späteren
Feature-Branches implementiert. Die Bildverarbeitung bleibt im Vision-Paket.
"""
import time
from collections import deque
from queue import Queue

from shared import TOPIC_PAYLOAD_TYPES, MQTTWrapper, PayloadInstance, TofPayload


class SensorHistory:
    """Sammelt Nachrichten eines MQTT-Topics in einem Ringpuffer.

    :param max_items: Maximale Anzahl gespeicherter Nachrichten.
    :param mqtt_wrapper: MQTT-Wrapper für das Topic-Abonnement.
    :param topic: MQTT-Topic, dessen Nachrichten gesammelt werden.
    """

    def __init__(self, max_items: int, mqtt_wrapper: MQTTWrapper, *, topic: str) -> None:
        """Abonniert ein Topic und erstellt den zugehörigen Ringpuffer.

        :param max_items: Maximale Anzahl gespeicherter Nachrichten.
        :param mqtt_wrapper: MQTT-Wrapper für das Topic-Abonnement.
        :param topic: MQTT-Topic, dessen Nachrichten gesammelt werden.
        """
        self._history: deque[PayloadInstance] = deque(maxlen=max_items)
        self.mqtt_wrapper = mqtt_wrapper
        self.mqtt_wrapper.subscribe(topic, self._append_event)

    def _append_event(self, payload: PayloadInstance) -> None:
        """Speichert eine neue Sensornachricht im begrenzten Verlauf.

        :param payload: Empfangene Sensornachricht.
        """
        self._history.append(payload)

    def get_events(self, lookback_period_ms: int) -> list[PayloadInstance]:
        """Gibt aktuelle Events aus dem angegebenen Zeitfenster zurück.

        Die Liste ist von neu nach alt sortiert.

        Example:
            Bei gespeicherten Events mit Alter 100 ms, 500 ms und 2_000 ms
            liefert `get_events(1_000)` die ersten beiden Events.

        :param lookback_period_ms: Zeitspanne, die in die Vergangenheit geschaut wird.
        :return: Passende Events, sortiert von neu nach alt.
        """
        events = []
        current_unix_time_ms = int(time.time() * 1000)
        for payload_event in reversed(self._history):
            time_difference = current_unix_time_ms - payload_event.timestamp_ms
            if time_difference <= lookback_period_ms:
                events.append(payload_event)
            else:
                break
        return events


class TofHistory(SensorHistory):
    """Sammelt ToF-Nachrichten und meldet kritische Abstandswerte.

    :param max_items: Maximale Anzahl gespeicherter Nachrichten.
    :param mqtt_wrapper: MQTT-Wrapper für das Topic-Abonnement.
    :param alert_queue: Queue für ToF-Werte unterhalb des Grenzwerts.
    :param topic: MQTT-Topic, dessen Nachrichten gesammelt werden.
    """

    def __init__(
        self,
        max_items: int,
        mqtt_wrapper: MQTTWrapper,
        alert_queue: Queue[TofPayload],
        *,
        topic: str,
    ) -> None:
        """Abonniert ein ToF-Topic und speichert die Alert-Queue.

        :param max_items: Maximale Anzahl gespeicherter Nachrichten.
        :param mqtt_wrapper: MQTT-Wrapper für das Topic-Abonnement.
        :param alert_queue: Queue für kritische ToF-Payloads.
        :param topic: MQTT-Topic, dessen Nachrichten gesammelt werden.
        """
        super().__init__(max_items, mqtt_wrapper, topic=topic)
        self._alert_queue = alert_queue

    def _append_event(self, payload: PayloadInstance) -> None:
        """Speichert eine ToF-Nachricht und meldet zu geringe Abstände.

        :param payload: Empfangene ToF-Payload.
        """
        super()._append_event(payload)
        if not isinstance(payload, TofPayload):
            raise TypeError("Payload für TofHistory muss eine TofPayload sein.")
        if payload.distance_cm < 150:
            self._alert_queue.put(payload)


def subscribe_sensors(max_items: int, mqtt_wrapper: MQTTWrapper) -> dict[str, SensorHistory]:
    """Abonniert alle bekannten MQTT-Topics und legt je Topic einen Ringpuffer an.

    :param max_items: Maximale Anzahl gespeicherter Nachrichten je Topic.
    :param mqtt_wrapper: MQTT-Wrapper für die Abonnements.
    :return: Verläufe, adressiert über ihr MQTT-Topic.
    """
    subscribed_sensors: dict[str, SensorHistory] = {}
    for topic in TOPIC_PAYLOAD_TYPES.keys():
        # Spezialfall für TofSensor
        history: SensorHistory
        if topic == "sensors/tof":
            history = TofHistory(
                max_items=max_items,
                mqtt_wrapper=mqtt_wrapper,
                topic=topic,
                alert_queue=Queue(maxsize=max_items),
            )
        else:
            history = SensorHistory(max_items=max_items, mqtt_wrapper=mqtt_wrapper, topic=topic)
        subscribed_sensors[topic] = history
    return subscribed_sensors


def check_unsafe_overtake() -> bool:
    """Platzhalter für die spätere Erkennung kritischer Überholvorgänge.

    :raises NotImplementedError: Bis die Ereignislogik implementiert ist.
    """
    raise NotImplementedError("Not implemented yet....")
