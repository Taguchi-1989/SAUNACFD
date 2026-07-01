"""CLI entry point for SaunaFlow harness."""

from __future__ import annotations

from pathlib import Path

import click

from harness import __version__


@click.group()
@click.version_option(version=__version__, prog_name="saunaflow")
def main() -> None:
    """SaunaFlow - Python harness for sauna CFD simulation."""


@main.command()
@click.argument("case_yaml", type=click.Path(exists=True))
def validate(case_yaml: str) -> None:
    """Validate a YAML case definition against the schema."""
    from harness.schema import load_and_validate

    errors = load_and_validate(case_yaml)
    if errors:
        for err in errors:
            click.echo(f"ERROR: {err}", err=True)
        raise SystemExit(1)
    click.echo("Valid.")


@main.command()
@click.argument("case_yaml", type=click.Path(exists=True))
@click.option("--output-dir", "-o", type=click.Path(), default=None,
              help="Output directory for the built case.")
def build(case_yaml: str, output_dir: str | None) -> None:
    """Build OpenFOAM case directory from YAML definition."""
    from harness.case_builder import build_case

    out = build_case(
        Path(case_yaml),
        output_dir=Path(output_dir) if output_dir else None,
    )
    click.echo(f"Case built: {out}")


@main.command()
@click.argument("case_dir", type=click.Path(exists=True))
@click.option("--mesh-only", is_flag=True, help="Only generate mesh, do not solve.")
@click.option("--solver", default="buoyantSimpleFoam", help="Solver executable name.")
@click.option("--timeout", default=3600, type=int, help="Solver timeout in seconds.")
def run(case_dir: str, mesh_only: bool, solver: str, timeout: int) -> None:
    """Run mesh generation and solver on a built case directory."""
    from harness.mesh_runner import run_mesh
    from harness.solver_runner import run_solver

    case_path = Path(case_dir)

    click.echo("Running blockMesh...")
    mesh_result = run_mesh(case_path)
    click.echo(f"Mesh: {mesh_result.cell_count} cells")

    if mesh_only:
        return

    click.echo(f"Running {solver}...")
    solver_result = run_solver(case_path, solver_name=solver, timeout=timeout)
    status = "CONVERGED" if solver_result.converged else "NOT converged"
    click.echo(f"Solver: {status} after {solver_result.iterations} iterations")

    if solver_result.final_residuals:
        click.echo("Final residuals:")
        for field, val in sorted(solver_result.final_residuals.items()):
            click.echo(f"  {field}: {val:.2e}")


@main.command()
@click.argument("case_dir", type=click.Path(exists=True))
@click.argument("case_yaml", type=click.Path(exists=True))
def report(case_dir: str, case_yaml: str) -> None:
    """Generate KPI report from solver results and case definition."""
    from harness.kpi import evaluate_all_kpis
    from harness.probe_parser import get_steady_state_values, parse_probe_file
    from harness.reporting import report_to_json, report_to_markdown
    from harness.schema import load_yaml
    from harness.validation import compare_probes, load_experimental_csv, time_average

    case_path = Path(case_dir)
    data = load_yaml(case_yaml)

    probe_names = [p["name"] for p in data.get("probes", [])]
    probe_file = case_path / "postProcessing" / "probes" / "0" / "T"

    if not probe_file.exists():
        click.echo(f"ERROR: Probe file not found: {probe_file}", err=True)
        raise SystemExit(1)

    probe_data = parse_probe_file(probe_file, probe_names)
    values = get_steady_state_values(probe_data)

    click.echo("Probe steady-state values:")
    for name, val in values.items():
        click.echo(f"  {name}: {val:.2f} K")

    time_series: list[float] | None = None
    t_upper_series: list[float] | None = None
    humidity_series: list[float] | None = None

    if probe_file.exists():
        probe_data = parse_probe_file(probe_file, probe_names)
        if probe_data:
            time_series = probe_data[0].times
            t_upper_series = next(
                (pd.values for pd in probe_data if pd.probe_name == "upper_bench"),
                None,
            )

    humidity_file = case_path / "postProcessing" / "probes" / "0" / "H2O"
    if humidity_file.exists():
        humidity_probe_data = parse_probe_file(humidity_file, probe_names)
        humidity_series = next(
            (pd.values for pd in humidity_probe_data if pd.probe_name == "upper_bench"),
            None,
        )

    baseline_temp = values.get("upper_bench", 0.0)
    if t_upper_series:
        baseline_temp = t_upper_series[0]

    aufguss_cfg = data.get("aufguss", {})
    beta_aug = aufguss_cfg.get("beta_aug", 0.0)
    aufguss_face_velocity = 0.0
    if beta_aug > 0:
        from harness.jet import free_jet_face_velocity
        aufguss_face_velocity = free_jet_face_velocity(
            aufguss_cfg.get("jet_velocity", 2.0),
            aufguss_cfg.get("jet_diameter", 0.15),
            aufguss_cfg.get("face_distance", 1.0),
        )

    # Compute perceived temperature accounting for humidity
    t_upper_k = values.get("upper_bench", 293.15)
    loyly_data = data.get("loyly", {})
    water_ml = loyly_data.get("water_ml", 0)
    # Rough humidity estimate for CLI path (full evaporation assumed)
    humidity_est = (water_ml / 1000.0) / 1.0 if water_ml > 0 else 0.0  # ~1 kg air mass
    from harness.simple_solver import _humid_air_properties
    perceived_props = _humid_air_properties(t_upper_k, humidity_est)
    perceived_temp_c = perceived_props["perceived_temp_c"]
    kpis = evaluate_all_kpis(
        probe_values=values,
        t_upper_series=t_upper_series,
        humidity_series=humidity_series,
        time_series=time_series,
        baseline_temp=baseline_temp,
        event_time=float(data.get("loyly", {}).get("time", 0.0)),
        beta_aug=beta_aug,
        perceived_temp_c=perceived_temp_c,
        aufguss_face_velocity=aufguss_face_velocity,
    )
    click.echo("\nKPI Results:")
    for kpi in kpis:
        status = f" [{kpi.pass_fail}]" if kpi.pass_fail else ""
        click.echo(f"  {kpi.kpi_id} {kpi.name}: {kpi.value} {kpi.unit}{status}")

    exp_csv = data.get("validation", {}).get("experimental_csv")
    if not exp_csv:
        return

    csv_path = Path(exp_csv)
    if not csv_path.is_absolute():
        csv_path = Path(case_yaml).resolve().parent / csv_path
    if not csv_path.exists():
        click.echo(f"\nWARNING: Experimental CSV not found: {csv_path}", err=True)
        return

    exp_data = load_experimental_csv(csv_path)
    exp_values: dict[str, float] = {}
    exp_times = exp_data.get("time")
    for name in probe_names:
        if name in exp_data:
            if exp_times is not None and len(exp_times) > 1:
                # Use the last 50% of experimental data (steady-state region)
                t_mid = (exp_times[0] + exp_times[-1]) / 2.0
                exp_values[name] = time_average(exp_data[name], exp_times, start=t_mid)
            else:
                exp_values[name] = float(exp_data[name][-1])

    report_obj = compare_probes(values, exp_values, case_name=data["case"]["name"])
    validation_dir = case_path / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    md_path = validation_dir / "report.md"
    json_path = validation_dir / "report.json"
    report_to_markdown(report_obj, md_path)
    report_to_json(report_obj, json_path)
    click.echo(f"\nValidation: {'PASS' if report_obj.overall_pass else 'FAIL'}")
    click.echo(f"  Markdown: {md_path}")
    click.echo(f"  JSON: {json_path}")


@main.command()
@click.argument("case_dir", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output markdown file path")
@click.option("--max-iter", default=50000, help="Max iterations per case")
def batch(case_dir: str, output: str | None, max_iter: int) -> None:
    """Run all YAML cases in a directory and generate comparison report."""
    from harness.batch import run_batch

    case_path = Path(case_dir)
    yamls = sorted(case_path.glob("*.yaml"))

    if not yamls:
        click.echo(f"No YAML files found in {case_dir}")
        return

    click.echo(f"Running {len(yamls)} cases from {case_dir}...")
    report = run_batch(yamls, max_iter=max_iter)

    md = report.summary_table()
    click.echo(md)

    if output:
        out_path = Path(output)
        out_path.write_text(md, encoding="utf-8")
        click.echo(f"\nReport saved to {out_path}")


@main.command()
@click.argument("case_yaml", type=click.Path(exists=True))
@click.option("--param", "-p", "params", multiple=True,
              help="Parameter as dotted.path[:rel_sigma], repeatable. "
                   "Defaults to heater power, wall conductivity, wall thickness.")
@click.option("--max-iter", default=4000, help="Max solver iterations per run")
@click.option("--output", "-o", default=None, help="Output markdown file path")
def sensitivity(case_yaml: str, params: tuple[str, ...], max_iter: int,
                output: str | None) -> None:
    """Parameter sensitivity & uncertainty bands for the two-zone ROM (C10)."""
    from harness.sensitivity import (
        ParamSpec,
        local_sensitivities,
        propagate_uncertainty,
        sensitivity_report_markdown,
    )

    if params:
        specs = []
        for raw in params:
            path, _, sig = raw.partition(":")
            specs.append(ParamSpec(path, rel_sigma=float(sig) if sig else 0.10))
    else:
        from harness.schema import load_yaml
        from harness.sensitivity import _get_dotted

        data = load_yaml(Path(case_yaml))
        candidates = [
            ("boundary_conditions.heater.power_kw", 0.10),
            ("boundary_conditions.heater.convective_fraction", 0.10),
            ("boundary_conditions.walls.conductivity", 0.20),
            ("boundary_conditions.walls.thickness", 0.20),
            ("boundary_conditions.walls.h_natural", 0.20),
        ]
        specs = []
        for path, sig in candidates:
            try:
                _get_dotted(data, path)
            except (KeyError, TypeError):
                continue
            specs.append(ParamSpec(path, rel_sigma=sig))
        if not specs:
            click.echo("No default parameters present in case; use --param.", err=True)
            raise SystemExit(1)

    case = Path(case_yaml)
    click.echo(f"Running sensitivity over {len(specs)} parameters...")
    sens = local_sensitivities(case, specs, max_iter=max_iter)
    bands = propagate_uncertainty(case, specs, max_iter=max_iter, sens=sens)
    md = sensitivity_report_markdown(sens, bands)
    click.echo(md)
    if output:
        Path(output).write_text(md, encoding="utf-8")
        click.echo(f"\nReport saved to {output}")


if __name__ == "__main__":
    main()
