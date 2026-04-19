"""DS18B20 temperature sensor driver for MicroPython (box internal temp)."""

import machine
import onewire
import ds18x20
import time


class DS18B20Sensor:
    """Read temperature from a DS18B20 1-Wire sensor.

    Used for monitoring the temperature inside the insulated box
    to protect the microcontroller from overheating.
    """

    def __init__(self, pin: int) -> None:
        ow = onewire.OneWire(machine.Pin(pin))
        self._ds = ds18x20.DS18X20(ow)
        self._roms = self._ds.scan()
        if not self._roms:
            print("WARNING: No DS18B20 sensor found on pin", pin)

    def read(self) -> float:
        """Read temperature [°C].

        Returns:
            Temperature in Celsius, or -999.0 if no sensor or read error.
        """
        if not self._roms:
            return -999.0
        try:
            self._ds.convert_temp()
            time.sleep_ms(750)  # DS18B20 conversion time
            return self._ds.read_temp(self._roms[0])
        except Exception:
            return -999.0
