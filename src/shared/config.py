"""Zentrale feste Einstellungen für Safe Cycle."""

from typing import Final

MQTT_BROKER_IP: Final = "127.0.0.1"
MQTT_BROKER_PORT: Final = 1883
CAMERA_PIPELINE: Final = (
    "libcamerasrc ! "
    "video/x-raw,width=640,height=640 ! "
    "videoconvert ! "
    "video/x-raw,format=BGR,width=640,height=640 ! "
    "appsink drop=true max-buffers=1 sync=false"
)
