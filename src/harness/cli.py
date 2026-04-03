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
    from harness.kpi import evaluate_phase1_kpis
    from harness.probe_parser import get_steady_state_values, parse_probe_file
    from harness.schema import load_yaml

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

    kpis = evaluate_phase1_kpis(values)
    click.echo("\nKPI Results:")
    for kpi in kpis:
        status = f" [{kpi.pass_fail}]" if kpi.pass_fail else ""
        click.echo(f"  {kpi.kpi_id} {kpi.name}: {kpi.value} {kpi.unit}{status}")


if __name__ == "__main__":
    main()
