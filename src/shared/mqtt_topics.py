"""Gemeinsame MQTT-Topics und zugehörige Payload-Typen."""

from typing import TypeAlias

from shared.data_models import GpsPayload, ImuPayload, RadarPayload, TofPayload, VisionPayload

PayloadType: TypeAlias = (
    type[GpsPayload]
    | type[ImuPayload]
    | type[RadarPayload]
    | type[TofPayload]
    | type[VisionPayload]
)

TOPIC_PAYLOAD_TYPES: dict[str, PayloadType] = {
    "sensors/radar": RadarPayload,
    "sensors/tof/left": TofPayload,
    "sensors/tof/right": TofPayload,
    "sensors/gps": GpsPayload,
    "sensors/imu": ImuPayload,
    "vision/vehicles": VisionPayload,
}
