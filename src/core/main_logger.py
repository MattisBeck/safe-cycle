"""Zentrale Synchronisierung und Protokollierung einer Fahrt.

MQTT-Abonnements, Ereignislogik, Ringpuffer und Dateiausgabe werden in späteren
Feature-Branches implementiert. Die Bildverarbeitung bleibt im Vision-Paket.
"""
import time
from collections import deque
from queue import Queue

from shared import (
    TOPIC_PAYLOAD_TYPES,
    Coordinates,
    GpsPayload,
    MQTTWrapper,
    PayloadInstance,
    TofPayload,
    Violation,
    VisionPayload,
)

UNSAFE_OVERTAKE_THRESHOLD_CM = 150
VISION_LOOKBACK_PERIOD_MS = 3_000
GPS_EVENT_WINDOW_MS = 3_000


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

    def get_events(
        self,
        lookback_period_ms: int,
        *,
        reference_timestamp_ms: int | None = None,
    ) -> list[PayloadInstance]:
        """Gibt aktuelle Events aus dem angegebenen Zeitfenster zurück.

        Die Liste ist von neu nach alt sortiert.

        Example:
            Bei gespeicherten Events mit Alter 100 ms, 500 ms und 2_000 ms
            liefert `get_events(1_000)` die ersten beiden Events.

        :param lookback_period_ms: Zeitspanne, die in die Vergangenheit geschaut wird.
        :param reference_timestamp_ms: Optionaler Bezugszeitpunkt statt der aktuellen Zeit.
        :return: Passende Events, sortiert von neu nach alt.
        """
        events: list[PayloadInstance] = []
        if reference_timestamp_ms is None:
            reference_timestamp_ms = int(time.time() * 1000)

        for payload_event in reversed(self._history):
            time_difference = reference_timestamp_ms - payload_event.timestamp_ms
            if time_difference < 0:
                continue
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
        if payload.distance_cm < UNSAFE_OVERTAKE_THRESHOLD_CM:
            self._alert_queue.put(payload)


def subscribe_topics(max_items: int, mqtt_wrapper: MQTTWrapper) -> dict[str, SensorHistory]:
    """Abonniert alle bekannten MQTT-Topics und legt je Topic einen Ringpuffer an.

    :param max_items: Maximale Anzahl gespeicherter Nachrichten je Topic.
    :param mqtt_wrapper: MQTT-Wrapper für die Abonnements.
    :return: Verläufe, adressiert über ihr MQTT-Topic.
    """
    subscribed_topics: dict[str, SensorHistory] = {}
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
        subscribed_topics[topic] = history
    return subscribed_topics


def check_unsafe_overtake(tof_payload: TofPayload, vision_history: SensorHistory) -> bool:
    """Prüft eine Abstandsunterschreitung auf ein erkanntes Fahrzeug.

    :param tof_payload: ToF-Messung als zeitlicher Bezugspunkt.
    :param vision_history: Verlauf der Vision-Payloads.
    :return: `True`, wenn Abstand und Fahrzeugerkennung zusammenpassen.
    """
    if not tof_payload.is_valid or tof_payload.distance_cm >= UNSAFE_OVERTAKE_THRESHOLD_CM:
        return False

    recent_events = vision_history.get_events(
        VISION_LOOKBACK_PERIOD_MS,
        reference_timestamp_ms=tof_payload.timestamp_ms,
    )
    return any(isinstance(event, VisionPayload) and event.found_vehicle for event in recent_events)


def gather_violation_data(tof_payload: TofPayload, gps_payload: GpsPayload) -> Violation:
    """Sammelt synchronisierte Messwerte für einen Abstandsverstoß.

    :param tof_payload: ToF-Messung des bereits bestätigten Verstoßes.
    :param gps_payload: Zeitlich zugeordnete GPS-Messung.
    :return: Daten für den späteren Eintrag in der Verstoßliste.
    """
    return Violation(
        timestamp=tof_payload.timestamp_ms // 1_000,
        coordinates=Coordinates(lat=gps_payload.latitude, lon=gps_payload.longitude),
        distance_cm=tof_payload.distance_cm,
        speed_kmh=gps_payload.speed_kmh,
    )


def get_nearest_event(history: SensorHistory, timestamp_ms: int) -> GpsPayload | None:
    """Sucht das zeitlich nächste gültige GPS-Ereignis.

    Bei gleichem zeitlichem Abstand wird das frühere Ereignis bevorzugt.

    :param history: Verlauf mit möglichen GPS-Payloads.
    :param timestamp_ms: Mittelpunkt des Suchfensters in Millisekunden.
    :return: Nächstes gültiges GPS-Payload oder `None`.
    """
    candidates = [
        event
        for event in list(history._history)
        if isinstance(event, GpsPayload)
        and event.satellites_connected > 0
        and abs(event.timestamp_ms - timestamp_ms) <= GPS_EVENT_WINDOW_MS
    ]
    if not candidates:
        return None

    return min(
        candidates,
        key=lambda event: (abs(event.timestamp_ms - timestamp_ms), event.timestamp_ms),
    )


def process_tof_alert(
    tof_payload: TofPayload,
    vision_history: SensorHistory,
    gps_history: SensorHistory,
) -> Violation | None:
    """Verarbeitet einen ToF-Alarm zu einem vollständigen Verstoß.

    :param tof_payload: Zu prüfender ToF-Alarm.
    :param vision_history: Verlauf der Fahrzeugerkennung.
    :param gps_history: Verlauf der GPS-Messungen.
    :return: Vollständiger Verstoß oder `None` bei fehlender Bestätigung.
    """
    if not check_unsafe_overtake(tof_payload, vision_history):
        return None

    gps_payload = get_nearest_event(gps_history, tof_payload.timestamp_ms)
    if gps_payload is None:
        return None

    return gather_violation_data(tof_payload, gps_payload)
