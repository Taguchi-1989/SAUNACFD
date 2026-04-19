"""DHT22 temperature/humidity sensor driver for MicroPython."""

import dht
import machine


class DHT22Sensor:
    """Read temperature and humidity from a DHT22 (AM2302) sensor.

    Operating range: -40 to 80°C, 0-100% RH.
    Minimum sampling interval: 2 seconds.
    """

    def __init__(self, pin: int) -> None:
        self._sensor = dht.DHT22(machine.Pin(pin))

    def read(self) -> tuple:
        """Read temperature [°C] and relative humidity [%RH].

        Returns:
            (temperature_c, humidity_rh_pct) tuple.
            Returns (None, None) on read failure.
        """
        try:
            self._sensor.measure()
            return self._sensor.temperature(), self._sensor.humidity()
        except OSError:
            return None, None
