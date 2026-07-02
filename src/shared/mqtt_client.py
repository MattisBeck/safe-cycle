"""Hilfsfunktionen für MQTT-Versand und JSON-Serialisierung.

MQTT nutzt ein Publish/Subscribe-Modell: Ein Client sendet eine Nachricht auf
ein Topic, und der Broker verteilt sie an alle Clients, die dieses Topic
abonniert haben.
"""

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from shared.mqtt_topics import TOPIC_PAYLOAD_TYPES, PayloadType

TOPIC_SCHEMA: dict[str, PayloadType] = TOPIC_PAYLOAD_TYPES


class MQTTWrapper:
    """Verbindet Dataclass-Payloads mit MQTT-Topics.

    Der Wrapper versteckt die Details des Paho-Clients. Der übrige Code muss
    dadurch nur wissen, auf welchem Topic eine Dataclass gesendet oder
    empfangen werden soll.
    """

    def __init__(self, broker_ip: str, broker_port: int) -> None:
        """Erstellt den MQTT-Client und startet den Nachrichtenaustausch.

        Der MQTT-Broker ist die zentrale Verteilstelle für Nachrichten.
        `loop_start()` startet die Netzwerk-Schleife im Hintergrund, damit
        eingehende Nachrichten verarbeitet werden, während das Programm
        weiterläuft.

        :param broker_ip: IP-Adresse oder Hostname des MQTT-Brokers.
        :param broker_port: Port des MQTT-Brokers.
        """
        # Der Paho-Client hält die TCP-Verbindung zum MQTT-Broker.
        self.mqttc = mqtt.Client(CallbackAPIVersion.VERSION2)

        # Zu jedem abonnierten Topic merken wir uns das Datenmodell und die Aktion.
        self._subscriptions: dict[str, tuple[PayloadType, Callable[[Any], None]]] = {}

        # Paho ruft diese Funktion automatisch auf, sobald eine Nachricht eintrifft.
        self.mqttc.on_message = self._on_message
        self.mqttc.connect(broker_ip, broker_port)
        self.mqttc.loop_start()

    def publish(self, topic: str, payload: object) -> None:
        """Sendet eine Dataclass als JSON-Nachricht auf ein MQTT-Topic.

        Ein Topic ist ein Kanal wie `"sensors/radar"`. Empfänger
        bekommen die Nachricht nur, wenn sie dieses Topic abonniert haben.

        :param topic: MQTT-Topic, auf dem die Nachricht veröffentlicht wird.
        :param payload: Zu versendende Dataclass mit MQTT-Nutzdaten.
        :raises TypeError: Wenn Topic oder Payload nicht zum gemeinsamen Schema passen.
        """
        if topic not in TOPIC_SCHEMA:
            raise TypeError(f"Topic: {topic} nicht gefunden.")
        if not is_dataclass(payload) or isinstance(payload, type):
            raise TypeError("Payload muss eine Dataclass sein.")

        expected_payload_type = TOPIC_SCHEMA[topic]
        if not isinstance(payload, expected_payload_type):
            raise TypeError(
                f"Payload für Topic {topic} muss {expected_payload_type.__name__} sein."
            )

        # JSON macht die Nachricht unabhängig vom Python-Prozess lesbar.
        payload_dict = asdict(payload)
        json_string = json.dumps(payload_dict)
        self.mqttc.publish(topic, json_string)

    def close(self) -> None:
        """Beendet die MQTT-Verbindung und die Hintergrundschleife."""
        self.mqttc.disconnect()
        self.mqttc.loop_stop()

    def subscribe(self, topic: str, action: Callable[[Any], None]) -> None:
        """Abonniert ein Topic und verknüpft es mit einer Callback-Funktion.

        Die Callback-Funktion `action` wird später für jede eingehende
        Nachricht auf diesem Topic ausgeführt. Sie erhält bereits die passende
        Payload-Dataclass, nicht die rohen JSON-Bytes.

        Beispiel:
            wrapper.subscribe("sensors/radar", handle_radar_payload)

        :param topic: MQTT-Topic, das abonniert werden soll.
        :param action: Callback für die deserialisierte Nachricht.
        :raises TypeError: Wenn für das Topic kein Payload-Typ bekannt ist.
        """
        if topic not in TOPIC_SCHEMA:
            raise TypeError(f"Topic: {topic} nicht gefunden.")

        # Das Schema legt fest, welche Dataclass aus der JSON-Nachricht entsteht.
        dataclass_schema = TOPIC_SCHEMA[topic]
        self._subscriptions[topic] = (dataclass_schema, action)

        # Erst dieses Abo teilt dem Broker mit, dass wir Nachrichten wollen.
        self.mqttc.subscribe(topic)

    def _on_message(self, _client: mqtt.Client, _userdata: object, msg: mqtt.MQTTMessage) -> None:
        """Verarbeitet eine eingehende MQTT-Nachricht aus dem Paho-Callback.

        Diese Methode wird nicht direkt vom Projektcode aufgerufen. Paho ruft
        sie auf, wenn der Broker eine Nachricht für ein abonniertes Topic
        liefert.

        :param _client: Paho-Client, der die Nachricht empfangen hat.
        :param _userdata: Frei nutzbare Paho-Zusatzdaten, hier nicht verwendet.
        :param msg: Rohes MQTT-Nachrichtenobjekt von Paho.
        """
        topic = msg.topic
        raw_json = msg.payload.decode("utf-8")

        # Nachrichten ohne registrierte Aktion werden ignoriert.
        if topic not in self._subscriptions:
            return None

        dataclass_schema, action = self._subscriptions[topic]

        # Aus JSON wird wieder die vereinbarte Dataclass, danach läuft die Aktion.
        blueprint_dict = json.loads(raw_json)
        ready_dataclass = dataclass_schema(**blueprint_dict)
        action(ready_dataclass)
        return None
