"""JSON line output over USB serial."""

import json


def send_line(data: dict) -> None:
    """Print a JSON-encoded line to USB serial (stdout).

    The host-side serial_logger.py reads these lines.
    """
    print(json.dumps(data))
