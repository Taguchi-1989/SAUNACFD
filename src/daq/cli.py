"""SaunaFlow DAQ CLI - Sensor data acquisition commands."""

from __future__ import annotations

from pathlib import Path

import click
import numpy as np

from daq.meta import generate_meta, save_meta
from daq.processor import detect_steady_state, process_raw


def _detect_raw_steady_states(
    raw_data: np.ndarray,
    window_s: float = 60.0,
    threshold_c_per_min: float = 0.1,
) -> list[tuple[str | None, float | None]]:
    """Detect steady state independently for each sensor in raw DAQ data."""
    raw_data = np.atleast_1d(raw_data)
    ok_mask = np.array([status in ("ok", "warn") for status in raw_data["status"]])
    field_names = raw_data.dtype.names or ()

    if "sensor_id" in field_names:
        sensor_ids = sorted(
            {str(value).strip() for value in raw_data["sensor_id"] if str(value).strip()}
        )
        if sensor_ids:
            results: list[tuple[str | None, float | None]] = []
            for sensor_id in sensor_ids:
                sensor_mask = np.array(
                    [str(value).strip() == sensor_id for value in raw_data["sensor_id"]]
                )
                mask = ok_mask & sensor_mask
                results.append(
                    (
                        sensor_id,
                        _detect_masked_steady_state(
                            raw_data, mask, window_s, threshold_c_per_min
                        ),
                    )
                )
            return results

    return [
        (
            None,
            _detect_masked_steady_state(
                raw_data, ok_mask, window_s, threshold_c_per_min
            ),
        )
    ]


def _detect_masked_steady_state(
    raw_data: np.ndarray,
    mask: np.ndarray,
    window_s: float,
    threshold_c_per_min: float,
) -> float | None:
    if not np.any(mask):
        return None
    times = np.asarray(raw_data["time_s"][mask], dtype=float)
    temps = np.asarray(raw_data["temp_c"][mask], dtype=float)
    return detect_steady_state(
        times,
        temps,
        window_s=window_s,
        threshold_c_per_min=threshold_c_per_min,
    )


def _print_steady_state_results(
    results: list[tuple[str | None, float | None]],
) -> None:
    for sensor_id, t_ss in results:
        label = f" for sensor {sensor_id}" if sensor_id is not None else ""
        if t_ss is not None:
            click.echo(f"Steady state{label} detected at t={t_ss:.1f}s")
        else:
            click.echo(f"Steady state{label} not detected within data")


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
    except ImportError as exc:
        click.echo("ERROR: pyserial not installed. Run: pip install pyserial", err=True)
        raise SystemExit(1) from exc

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
@click.option("--probe", default=None, help="Probe name (overrides session metadata)")
@click.option(
    "--meta",
    "meta_yaml",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Session metadata YAML for probe mapping and calibration",
)
@click.option("--output", "-o", default=None, type=click.Path(), help="Output processed CSV")
def process(raw_csv: str, probe: str | None, meta_yaml: str | None, output: str | None) -> None:
    """Convert raw CSV to validation-compatible format."""
    raw_path = Path(raw_csv)

    if output is None:
        stem = raw_path.stem.replace("_raw", "")
        output_path = raw_path.parent.parent / "processed" / f"{stem}_validation.csv"
    else:
        output_path = Path(output)

    result = process_raw(
        raw_path,
        output_path,
        probe_name=probe,
        meta_yaml=Path(meta_yaml) if meta_yaml is not None else None,
    )
    click.echo(f"Processed CSV: {result}")

    # Detect steady state from raw data
    raw_data = np.genfromtxt(
        raw_path, delimiter=",", names=True, dtype=None, encoding="utf-8"
    )
    raw_data = np.atleast_1d(raw_data)
    _print_steady_state_results(_detect_raw_steady_states(raw_data))


@daq.command("steady-state")
@click.argument("raw_csv", type=click.Path(exists=True, dir_okay=False))
@click.option("--window", "window_s", default=60.0, type=click.FloatRange(min=0.1))
@click.option(
    "--threshold",
    "threshold_c_per_min",
    default=0.1,
    type=click.FloatRange(min=0.0),
    help="Maximum absolute temperature rate [C/min]",
)
def steady_state_cmd(
    raw_csv: str,
    window_s: float,
    threshold_c_per_min: float,
) -> None:
    """Detect steady-state arrival in a raw single- or multi-sensor CSV."""
    raw_data = np.genfromtxt(
        Path(raw_csv), delimiter=",", names=True, dtype=None, encoding="utf-8"
    )
    results = _detect_raw_steady_states(
        raw_data,
        window_s=window_s,
        threshold_c_per_min=threshold_c_per_min,
    )
    _print_steady_state_results(results)


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
