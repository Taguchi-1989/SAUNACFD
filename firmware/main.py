"""SaunaFlow DAQ firmware - Main entry point for MicroPython.

Reads DHT22 (sauna air temp/humidity) and DS18B20 (box internal temp),
outputs JSON lines over USB serial for the host-side logger to capture.

Deploy to Pico W or ESP32 by copying firmware/ contents to the device.
"""

import time

from config import (
    BOX_TEMP_SHUTDOWN_C,
    BOX_TEMP_WARN_C,
    DHT22_PIN,
    DS18B20_PIN,
    SAMPLE_INTERVAL_S,
)
from sensors.dht22 import DHT22Sensor
from sensors.ds18b20 import DS18B20Sensor
from serial_out import send_line


def determine_status(box_temp_c: float) -> str:
    """Determine safety status based on box temperature."""
    if box_temp_c >= BOX_TEMP_SHUTDOWN_C:
        return "shutdown"
    if box_temp_c >= BOX_TEMP_WARN_C:
        return "warn"
    return "ok"


def main() -> None:
    print("SaunaFlow DAQ starting...")

    dht_sensor = DHT22Sensor(DHT22_PIN)
    box_sensor = DS18B20Sensor(DS18B20_PIN)

    # Use ticks_ms for elapsed time calculation
    start_ms = time.ticks_ms()

    while True:
        elapsed_ms = time.ticks_diff(time.ticks_ms(), start_ms)
        time_s = elapsed_ms / 1000.0

        temp_c, rh_pct = dht_sensor.read()
        box_temp_c = box_sensor.read()

        # Handle sensor read failures
        if temp_c is None:
            temp_c = -999.0
            rh_pct = -999.0

        status = determine_status(box_temp_c)

        send_line({
            "time_s": round(time_s, 1),
            "temp_c": temp_c,
            "rh_pct": rh_pct,
            "box_temp_c": round(box_temp_c, 1),
            "status": status,
        })

        if status == "shutdown":
            print("BOX TEMPERATURE CRITICAL - SHUTTING DOWN")
            break

        time.sleep(SAMPLE_INTERVAL_S)


main()
