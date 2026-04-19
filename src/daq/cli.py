"""SaunaFlow DAQ CLI - Sensor data acquisition commands."""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
@click.version_option(package_name="saunaflow")
def daq() -> None:
    """SaunaFlow DAQ - Sensor data acquisition for CFD validation."""


@daq.command()
@click.option("--port", required=True, help="Serial port (e.g. COM3, /dev/ttyUSB0)")
@click.option("--baudrate", default=115200, help="Serial baud rate")
@click.option("--duration", default=1500, type=int, help="Session duration in seconds")
@click.option("--output", "-o", default=None, type=click.Path(), help="Output raw CSV path")
def log(port: str, baudrate: int, duration: int, output: str | None) -> None:
    """Record sensor data from serial port to raw CSV."""
    try:
        import serial as pyserial  # noqa: F811
    except ImportError:
        click.echo("ERROR: pyserial not installed. Run: pip install pyserial", err=True)
        raise SystemExit(1)

    from daq.serial_logger import log_session

    if output is None:
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"experiments/raw/session_{ts}_raw.csv"

    output_path = Path(output)
    click.echo(f"Logging to {output_path} for {duration}s from {port}@{baudrate}")

    ser = pyserial.Serial(port, baudrate, timeout=5)
    try:
        result = log_session(ser, duration_s=duration, output_path=output_path)
        click.echo(f"Session saved: {result}")
    finally:
        ser.close()


@daq.command()
@click.argument("raw_csv", type=click.Path(exists=True))
@click.option("--probe", default="lower_bench", help="Probe name for output column")
@click.option("--output", "-o", default=None, type=click.Path(), help="Output processed CSV")
def process(raw_csv: str, probe: str, output: str | None) -> None:
    """Convert raw CSV to validation-compatible format."""
    from daq.processor import detect_steady_state, process_raw

    import numpy as np

    raw_path = Path(raw_csv)

    if output is None:
        stem = raw_path.stem.replace("_raw", "")
        output_path = raw_path.parent.parent / "processed" / f"{stem}_validation.csv"
    else:
        output_path = Path(output)

    result = process_raw(raw_path, output_path, probe_name=probe)
    click.echo(f"Processed CSV: {result}")

    # Detect steady state from raw data
    raw_data = np.genfromtxt(
        raw_path, delimiter=",", names=True, dtype=None, encoding="utf-8"
    )
    raw_data = np.atleast_1d(raw_data)
    ok_mask = np.array([s in ("ok", "warn") for s in raw_data["status"]])
    if np.any(ok_mask):
        times = np.asarray(raw_data["time_s"][ok_mask], dtype=float)
        temps = np.asarray(raw_data["temp_c"][ok_mask], dtype=float)
        t_ss = detect_steady_state(times, temps)
        if t_ss is not None:
            click.echo(f"Steady state detected at t={t_ss:.1f}s")
        else:
            click.echo("Steady state not detected within data")


@daq.command("meta")
@click.argument("raw_csv", type=click.Path(exists=True))
@click.option("--session-id", required=True, help="Session identifier")
@click.option("--sensor-id", default="DHT22-001", help="Sensor identifier")
@click.option("--cable-length", default=0.3, type=float, help="Cable length [m]")
@click.option("--probe", default="lower_bench", help="Probe name")
@click.option("--probe-y", default=0.8, type=float, help="Probe height [m]")
@click.option("--notes", default="", help="Session notes")
@click.option("--output", "-o", default=None, type=click.Path(), help="Output meta YAML")
def meta_cmd(
    raw_csv: str,
    session_id: str,
    sensor_id: str,
    cable_length: float,
    probe: str,
    probe_y: float,
    notes: str,
    output: str | None,
) -> None:
    """Generate session metadata YAML from raw CSV."""
    from daq.meta import generate_meta, save_meta
    from daq.processor import detect_steady_state

    import numpy as np

    raw_path = Path(raw_csv)

    # Detect steady state
    raw_data = np.genfromtxt(
        raw_path, delimiter=",", names=True, dtype=None, encoding="utf-8"
    )
    raw_data = np.atleast_1d(raw_data)
    ok_mask = np.array([s in ("ok", "warn") for s in raw_data["status"]])
    t_ss = None
    if np.any(ok_mask):
        times = np.asarray(raw_data["time_s"][ok_mask], dtype=float)
        temps = np.asarray(raw_data["temp_c"][ok_mask], dtype=float)
        t_ss = detect_steady_state(times, temps)

    meta = generate_meta(
        session_id=session_id,
        sensor_id=sensor_id,
        cable_length_m=cable_length,
        probe_name=probe,
        probe_y=probe_y,
        steady_state_reached_s=t_ss,
        notes=notes,
    )

    if output is None:
        stem = raw_path.stem.replace("_raw", "")
        output_path = raw_path.parent.parent / "meta" / f"{stem}_meta.yaml"
    else:
        output_path = Path(output)

    result = save_meta(meta, output_path)
    click.echo(f"Metadata saved: {result}")
    if t_ss is not None:
        click.echo(f"Steady state detected at t={t_ss:.1f}s")
