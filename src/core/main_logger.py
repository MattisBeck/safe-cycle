"""Zentrale Synchronisierung und Orchestrierung einer aufgezeichneten Fahrt.

Während einer Fahrt laufen zwei Abläufe gleichzeitig:

1. Paho-MQTT empfängt Nachrichten in einem Hintergrundthread und ruft die
   abonnierten Callback-Funktionen auf.
2. `run_ride` läuft in der eigentlichen Fahrt-Schleife und wertet regelmäßig
   gesammelte Nachrichten aus.

Histories speichern die zuletzt empfangenen Sensordaten. Queues übergeben
einzelne Alarme sicher vom MQTT-Hintergrundthread an die Fahrt-Schleife.
Locks verhindern, dass beide Abläufe denselben veränderlichen Zustand zur
gleichen Zeit lesen und schreiben.
"""
import signal
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from types import FrameType
from typing import TypeAlias
from zoneinfo import ZoneInfo

from core.ride_writer import write_ride_data
from core.vehicle_approach import (
    APPROACH_LOOKBACK_PERIOD_MS,
    VehicleApproachState,
    classify_vehicle_approach,
)
from shared import (
    TOPIC_PAYLOAD_TYPES,
    Coordinates,
    GpsPayload,
    MQTTWrapper,
    PayloadInstance,
    RideData,
    RoutePoint,
    TofPayload,
    Violation,
    VisionPayload,
)

UNSAFE_OVERTAKE_THRESHOLD_CM = 150
VISION_LOOKBACK_PERIOD_MS = APPROACH_LOOKBACK_PERIOD_MS
GPS_EVENT_WINDOW_MS = 3_000
RIDE_TIME_ZONE = ZoneInfo("Europe/Berlin")
DEFAULT_RIDE_OUTPUT_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "rides"

PayloadAction: TypeAlias = Callable[[PayloadInstance], None]


class SensorHistory:
    """Sammelt Nachrichten eines MQTT-Topics in einem Ringpuffer.

    :param max_items: Maximale Anzahl gespeicherter Nachrichten.
    :param mqtt_wrapper: MQTT-Wrapper für das Topic-Abonnement.
    :param topic: MQTT-Topic, dessen Nachrichten gesammelt werden.
    """

    def __init__(
        self,
        max_items: int,
        mqtt_wrapper: MQTTWrapper,
        *,
        topic: str,
        event_action: PayloadAction | None = None,
    ) -> None:
        """Abonniert ein Topic und erstellt den zugehörigen Ringpuffer.

        :param max_items: Maximale Anzahl gespeicherter Nachrichten.
        :param mqtt_wrapper: MQTT-Wrapper für das Topic-Abonnement.
        :param topic: MQTT-Topic, dessen Nachrichten gesammelt werden.
        :param event_action: Optionale Aktion nach dem Speichern einer Nachricht.
        """
        self._history: deque[PayloadInstance] = deque(maxlen=max_items)

        # MQTT fügt im Hintergrund neue Payloads hinzu, während die Fahrt-Schleife
        # möglicherweise gerade daraus liest. Der Lock erlaubt immer nur einem
        # dieser Abläufe gleichzeitig den Zugriff auf den Ringpuffer.
        self._history_lock = threading.Lock()
        self._event_action = event_action
        self.mqtt_wrapper = mqtt_wrapper

        # Der MQTT-Wrapper ruft `_append_event` später automatisch im
        # Paho-Hintergrundthread auf, sobald eine Nachricht für das Topic eintrifft.
        self.mqtt_wrapper.subscribe(topic, self._append_event)

    def _append_event(self, payload: PayloadInstance) -> None:
        """Speichert eine neue Sensornachricht im begrenzten Verlauf.

        :param payload: Empfangene Sensornachricht.
        """
        # Der Lock wird nur für das eigentliche Anhängen gehalten. Die optionale
        # Folgeaktion läuft danach, damit MQTT nicht unnötig lange ausgesperrt wird.
        with self._history_lock:
            self._history.append(payload)
        if self._event_action is not None:
            self._event_action(payload)

    def snapshot(self) -> list[PayloadInstance]:
        """Gibt eine threadsichere Kopie des aktuellen Verlaufs zurück.

        Die Kopie ist ein kurzer, unveränderter Blick auf den aktuellen Stand.
        Nach dem Kopieren darf MQTT sofort weiter in den Ringpuffer schreiben,
        während die Fahrt-Schleife die zurückgegebene Liste in Ruhe auswertet.
        """
        with self._history_lock:
            return list(self._history)

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

        # Auf dem Snapshot kann ohne Lock gefiltert werden. Neue MQTT-Nachrichten
        # landen parallel in der History und werden im nächsten Aufruf berücksichtigt.
        for payload_event in reversed(self.snapshot()):
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
        event_action: PayloadAction | None = None,
    ) -> None:
        """Abonniert ein ToF-Topic und speichert die Alert-Queue.

        :param max_items: Maximale Anzahl gespeicherter Nachrichten.
        :param mqtt_wrapper: MQTT-Wrapper für das Topic-Abonnement.
        :param alert_queue: Queue für kritische ToF-Payloads.
        :param topic: MQTT-Topic, dessen Nachrichten gesammelt werden.
        :param event_action: Optionale Aktion nach dem Speichern einer Nachricht.
        """
        super().__init__(
            max_items,
            mqtt_wrapper,
            topic=topic,
            event_action=event_action,
        )

        # `Queue` ist für die Übergabe zwischen Threads gedacht: MQTT legt den
        # Alarm hinein, die Fahrt-Schleife holt ihn später wieder heraus.
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


class RideSession:
    """Sammelt Route und Verstöße einer laufenden Fahrt im Speicher."""

    def __init__(self, start_timestamp_ms: int) -> None:
        """Erstellt eine aktive Fahrt mit festem Startzeitpunkt.

        :param start_timestamp_ms: Unix-Startzeit der Fahrt in Millisekunden.
        """
        start_datetime = datetime.fromtimestamp(start_timestamp_ms / 1_000, tz=RIDE_TIME_ZONE)
        self._ride_id = start_datetime.strftime("tour_%Y_%m_%d_%H%M")
        self._start_timestamp_ms = start_timestamp_ms
        self._route_logs: list[RoutePoint] = []
        self._violations: list[Violation] = []
        self._is_finished = False

    @classmethod
    def start(cls, start_timestamp_ms: int) -> "RideSession":
        """Startet eine neue Fahrt.

        :param start_timestamp_ms: Unix-Startzeit der Fahrt in Millisekunden.
        :return: Aktive Fahrt zum Sammeln von Messwerten.
        """
        return cls(start_timestamp_ms)

    def add_gps_payload(self, gps_payload: GpsPayload) -> bool:
        """Fügt ein gültiges GPS-Paket zur gefahrenen Route hinzu.

        :param gps_payload: Zu speichernde GPS-Messung.
        :return: `True`, wenn die Messung aufgenommen wurde.
        :raises ValueError: Wenn die Fahrt bereits beendet wurde.
        """
        self._ensure_active()
        if gps_payload.satellites_connected <= 0:
            return False

        self._route_logs.append(
            RoutePoint(
                timestamp=gps_payload.timestamp_ms // 1_000,
                lat=gps_payload.latitude,
                lon=gps_payload.longitude,
            )
        )
        return True

    def add_violation(self, violation: Violation) -> None:
        """Fügt einen bestätigten Abstandsverstoß zur Fahrt hinzu.

        :param violation: Vollständiger Abstandsverstoß.
        :raises ValueError: Wenn die Fahrt bereits beendet wurde.
        """
        self._ensure_active()
        self._violations.append(violation)

    def finish(self, end_timestamp_ms: int) -> RideData:
        """Beendet die Fahrt und gibt ihre vollständigen Daten zurück.

        :param end_timestamp_ms: Unix-Endzeit der Fahrt in Millisekunden.
        :return: Vollständige Daten der abgeschlossenen Fahrt.
        :raises ValueError: Bei ungültiger Endzeit oder bereits beendeter Fahrt.
        """
        self._ensure_active()
        if end_timestamp_ms < self._start_timestamp_ms:
            raise ValueError("Die Endzeit darf nicht vor der Startzeit liegen.")

        self._is_finished = True
        return RideData(
            ride_id=self._ride_id,
            start_time=self._start_timestamp_ms // 1_000,
            end_time=end_timestamp_ms // 1_000,
            route_logs=list(self._route_logs),
            violations=list(self._violations),
        )

    def _ensure_active(self) -> None:
        """Verhindert Änderungen an einer bereits beendeten Fahrt."""
        if self._is_finished:
            raise ValueError("Die Fahrt wurde bereits beendet.")


class RideOrchestrator:
    """Verbindet MQTT-Historien mit dem Zustand einer laufenden Fahrt.

    MQTT sammelt fortlaufend GPS-, Vision- und ToF-Daten. Der Orchestrator
    übernimmt daraus GPS-Punkte für die Route und hält kritische ToF-Messungen
    zunächst zurück. Erst nach Ablauf des GPS-Zeitfensters entscheidet er, ob
    aus einer Messung ein vollständiger Abstandsverstoß wird.
    """

    def __init__(
        self,
        start_timestamp_ms: int,
        mqtt_wrapper: MQTTWrapper,
        *,
        max_history_items: int,
    ) -> None:
        """Startet eine Session und richtet alle Topic-Historien ein.

        :param start_timestamp_ms: Unix-Startzeit der Fahrt in Millisekunden.
        :param mqtt_wrapper: MQTT-Wrapper für die Topic-Abonnements.
        :param max_history_items: Maximale Anzahl Payloads je History.
        """
        # GPS-Payloads kommen im MQTT-Hintergrundthread an. `process_pending`
        # und `finish` laufen dagegen in der Fahrt-Schleife. Dieser Lock schützt
        # die gemeinsam verwendete RideSession und die Pending-Liste.
        self._lock = threading.Lock()
        self._session = RideSession.start(start_timestamp_ms)

        # Pending bedeutet: Der ToF-Alarm ist bekannt, aber das symmetrische
        # GPS-Fenster von aktuell drei Sekunden ist noch nicht vollständig abgelaufen.
        self._pending_tof_alerts: list[TofPayload] = []

        # Diese Queue darf den MQTT-Callback beim Fahrtende niemals blockieren.
        # Deshalb hat sie bewusst keine maximale Größe. Normalerweise wird sie
        # alle 50 ms geleert, sodass sie nur sehr kurz Payloads enthält.
        self._tof_alert_queue: Queue[TofPayload] = Queue()
        self._is_finished = False
        self._histories = subscribe_topics(
            max_items=max_history_items,
            mqtt_wrapper=mqtt_wrapper,
            topic_actions={"sensors/gps": self._record_gps_payload},
            tof_alert_queue=self._tof_alert_queue,
        )

    def process_pending(self, current_timestamp_ms: int) -> int:
        """Verarbeitet ToF-Alarme mit vollständig abgelaufenem GPS-Fenster.

        :param current_timestamp_ms: Aktuelle Unix-Zeit in Millisekunden.
        :return: Anzahl neu hinzugefügter Verstöße.
        :raises ValueError: Wenn die Fahrt bereits beendet wurde.
        """
        with self._lock:
            self._ensure_active()

            # Zuerst werden alle seit dem letzten Durchlauf von MQTT empfangenen
            # Alarme in die lokale Pending-Liste übernommen.
            self._drain_tof_alert_queue()

            # Ein Alarm ist erst reif, wenn auch GPS-Pakete bis aktuell drei Sekunden
            # nach seinem Messzeitpunkt hätten eintreffen können.
            ready_alerts = [
                alert
                for alert in self._pending_tof_alerts
                if alert.timestamp_ms + GPS_EVENT_WINDOW_MS <= current_timestamp_ms
            ]
            self._pending_tof_alerts = [
                alert
                for alert in self._pending_tof_alerts
                if alert.timestamp_ms + GPS_EVENT_WINDOW_MS > current_timestamp_ms
            ]

            # Reife Alarme werden aus der Pending-Liste entfernt und genau in
            # diesem Durchlauf ausgewertet. So entsteht kein Verstoß doppelt.
            return self._process_alerts(ready_alerts)

    def finish(self, end_timestamp_ms: int) -> RideData:
        """Verarbeitet offene Alarme und beendet die Fahrt.

        MQTT muss vor diesem Aufruf beendet werden, damit keine neuen Payloads
        während des finalen Flushs eintreffen.

        :param end_timestamp_ms: Unix-Endzeit der Fahrt in Millisekunden.
        :return: Vollständige Daten der abgeschlossenen Fahrt.
        :raises ValueError: Wenn die Fahrt bereits beendet wurde.
        """
        with self._lock:
            self._ensure_active()

            # `run_ride` hat MQTT vor diesem Aufruf bereits geschlossen. Daher
            # können beim Leeren keine neuen Payloads mehr dazwischenkommen.
            self._drain_tof_alert_queue()

            # Beim Fahrtende warten wir nicht weitere drei Sekunden. Alle noch
            # offenen Alarme werden mit den bereits vorhandenen Daten geprüft.
            self._process_alerts(self._pending_tof_alerts)
            self._pending_tof_alerts = []
            ride_data = self._session.finish(end_timestamp_ms)
            self._is_finished = True
            return ride_data

    def _record_gps_payload(self, payload: PayloadInstance) -> None:
        """Übernimmt ein GPS-Payload aus dem MQTT-Hintergrundthread in die Route."""
        if not isinstance(payload, GpsPayload):
            raise TypeError("Das GPS-Topic muss eine GpsPayload liefern.")
        with self._lock:
            if not self._is_finished:
                self._session.add_gps_payload(payload)

    def _drain_tof_alert_queue(self) -> None:
        """Überführt alle empfangenen ToF-Alarme in die Pending-Liste.

        `get_nowait` wartet nicht auf eine neue Nachricht. Die Exception `Empty`
        ist hier kein Fehler, sondern das normale Signal, dass die Queue für
        diesen Verarbeitungszyklus vollständig geleert wurde.
        """
        while True:
            try:
                self._pending_tof_alerts.append(self._tof_alert_queue.get_nowait())
            except Empty:
                return

    def _process_alerts(self, alerts: list[TofPayload]) -> int:
        """Prüft Alarme und fügt bestätigte Verstöße zur Session hinzu."""
        vision_history = self._histories["vision/vehicles"]
        gps_history = self._histories["sensors/gps"]
        added_violations = 0

        for alert in alerts:
            # Diese Funktion verbindet die drei fachlichen Schritte: Vision
            # bestätigen, nächstes GPS suchen und Violation-Daten erzeugen.
            violation = process_tof_alert(alert, vision_history, gps_history)
            if violation is not None:
                self._session.add_violation(violation)
                added_violations += 1

        return added_violations

    def _ensure_active(self) -> None:
        """Verhindert Verarbeitung nach dem Fahrtabschluss."""
        if self._is_finished:
            raise ValueError("Die Fahrt wurde bereits beendet.")


def subscribe_topics(
    max_items: int,
    mqtt_wrapper: MQTTWrapper,
    *,
    topic_actions: Mapping[str, PayloadAction] | None = None,
    tof_alert_queue: Queue[TofPayload] | None = None,
) -> dict[str, SensorHistory]:
    """Abonniert alle bekannten MQTT-Topics und legt je Topic einen Ringpuffer an.

    :param max_items: Maximale Anzahl gespeicherter Nachrichten je Topic.
    :param mqtt_wrapper: MQTT-Wrapper für die Abonnements.
    :param topic_actions: Optionale Aktionen für empfangene Topic-Payloads.
    :param tof_alert_queue: Optional vorgegebene Queue für kritische ToF-Payloads.
    :return: Verläufe, adressiert über ihr MQTT-Topic.
    """
    actions = topic_actions if topic_actions is not None else {}
    alert_queue = (
        tof_alert_queue if tof_alert_queue is not None else Queue(maxsize=max_items)
    )
    subscribed_topics: dict[str, SensorHistory] = {}
    for topic in TOPIC_PAYLOAD_TYPES.keys():
        # Beide seitlichen ToF-Topics speisen dieselbe Alarm-Queue.
        history: SensorHistory
        if TOPIC_PAYLOAD_TYPES[topic] is TofPayload:
            history = TofHistory(
                max_items=max_items,
                mqtt_wrapper=mqtt_wrapper,
                topic=topic,
                alert_queue=alert_queue,
                event_action=actions.get(topic),
            )
        else:
            history = SensorHistory(
                max_items=max_items,
                mqtt_wrapper=mqtt_wrapper,
                topic=topic,
                event_action=actions.get(topic),
            )
        subscribed_topics[topic] = history
    return subscribed_topics


def check_unsafe_overtake(tof_payload: TofPayload, vision_history: SensorHistory) -> bool:
    """Prüft eine Abstandsunterschreitung auf ein sich näherndes Fahrzeug.

    :param tof_payload: ToF-Messung als zeitlicher Bezugspunkt.
    :param vision_history: Verlauf der Vision-Payloads.
    :return: `True`, wenn Abstand und Annäherungserkennung zusammenpassen.
    """
    if not tof_payload.is_valid or tof_payload.distance_cm >= UNSAFE_OVERTAKE_THRESHOLD_CM:
        return False

    recent_events = vision_history.get_events(
        VISION_LOOKBACK_PERIOD_MS,
        reference_timestamp_ms=tof_payload.timestamp_ms,
    )
    vision_events = [event for event in recent_events if isinstance(event, VisionPayload)]
    approach_state = classify_vehicle_approach(
        vision_events,
        reference_timestamp_ms=tof_payload.timestamp_ms,
    )
    return approach_state is VehicleApproachState.APPROACHING


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
        for event in history.snapshot()
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


def current_time_ms() -> int:
    """Gibt die aktuelle Unix-Zeit in Millisekunden zurück."""
    return int(time.time() * 1_000)


def run_ride(
    output_directory: Path,
    stop_event: threading.Event,
    *,
    max_history_items: int = 1_000,
    poll_interval_s: float = 0.05,
    clock_ms: Callable[[], int] = current_time_ms,
) -> Path:
    """Orchestriert eine vollständige Fahrt bis zur JSON-Ausgabe.

    Die Funktion erstellt ihren MQTT-Wrapper selbst und schließt ihn bei
    normalem Ende sowie bei Fehlern.

    :param output_directory: Zielverzeichnis für abgeschlossene Fahrten.
    :param stop_event: Signal zum Beenden der laufenden Fahrt.
    :param max_history_items: Maximale Anzahl Payloads je Topic-History.
    :param poll_interval_s: Wartezeit zwischen zwei Verarbeitungszyklen.
    :param clock_ms: Injizierbare Uhr mit Unix-Zeit in Millisekunden.
    :return: Pfad der geschriebenen Fahrtdatei.
    """
    mqtt_wrapper = MQTTWrapper()
    try:
        orchestrator = RideOrchestrator(
            start_timestamp_ms=clock_ms(),
            mqtt_wrapper=mqtt_wrapper,
            max_history_items=max_history_items,
        )

        # `Event` ist ein threadsicheres Stoppsignal. Solange es nicht gesetzt
        # ist, wartet die Schleife höchstens `poll_interval_s` und verarbeitet
        # danach die inzwischen gereiften ToF-Alarme.
        while not stop_event.wait(poll_interval_s):
            orchestrator.process_pending(clock_ms())
    finally:
        # `finally` wird auch bei Exceptions und Ctrl+C ausgeführt. MQTT muss
        # sicher gestoppt werden, damit kein Hintergrund-Callback weiterläuft.
        mqtt_wrapper.close()

    # Erst nach dem MQTT-Stopp werden letzte Alarme ausgewertet. Danach ist die
    # Fahrt vollständig und kann mit genau einem Dateizugriff gespeichert werden.
    ride_data = orchestrator.finish(clock_ms())
    return write_ride_data(ride_data, output_directory)


def main() -> None:
    """Startet die Fahrtaufzeichnung mit dem Standard-Ausgabeverzeichnis."""
    stop_event = threading.Event()

    def request_stop(_signal_number: int, _frame: FrameType | None) -> None:
        """Fordert bei einem Prozesssignal ein geordnetes Fahrtende an."""
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    run_ride(DEFAULT_RIDE_OUTPUT_DIRECTORY, stop_event)


if __name__ == "__main__":
    main()
