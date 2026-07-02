"""Gemeinsame MQTT-Topics und zugehörige Payload-Modelle."""

from shared.data_models import GpsPayload, ImuPayload, PayloadType, RadarPayload, TofPayload, VisionPayload

TOPIC_PAYLOAD_TYPES: dict[str, PayloadType] = {
    "sensors/radar": RadarPayload,
    "sensors/tof": TofPayload,
    "sensors/gps": GpsPayload,
    "sensors/imu": ImuPayload,
    "vision/vehicles": VisionPayload,
}
