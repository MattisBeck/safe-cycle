#!/bin/bash
echo "Starte Sensoren"

sudo PYTHONPATH=src .venv/bin/python -m sensors.gps_node &
sudo PYTHONPATH=src .venv/bin/python -m sensors.imu_node &
sudo PYTHONPATH=src .venv/bin/python -m sensors.radar_node &
sudo PYTHONPATH=src .venv/bin/python -m sensors.tof_node_left &
sudo PYTHONPATH=src .venv/bin/python -m sensors.tof_node_right &

echo "Alle Sensoren online"