"""Pin assignments and configuration for sauna DAQ firmware."""

# DHT22 data pin (external sensor, sauna air)
DHT22_PIN = 15

# DS18B20 data pin (internal sensor, box temperature)
DS18B20_PIN = 14

# Sampling interval in seconds (DHT22 minimum is 2s)
SAMPLE_INTERVAL_S = 2

# Box temperature safety thresholds [°C]
BOX_TEMP_WARN_C = 50
BOX_TEMP_SHUTDOWN_C = 60

# Serial baud rate (must match host-side serial_logger)
BAUDRATE = 115200
