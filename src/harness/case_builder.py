"""Case definition -> OpenFOAM directory structure builder."""

from __future__ import annotations

import shutil
from pathlib import Path

import jinja2

from harness.schema import load_and_validate, load_yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMPLATE_DIR = _PROJECT_ROOT / "foam_templates" / "base_case"
_RESULTS_DIR = _PROJECT_ROOT / "results"

# Cells per meter for each mesh level
_MESH_DENSITY: dict[str, int] = {
    "M0": 8,   # ~8/m -> 24x20x20 = ~9600 cells (coarse 2D-ish)
    "M1": 16,  # ~16/m -> ~48x40x40 = ~76800
    "M2": 28,  # ~28/m -> ~84x70x70 = ~411600
    "M3": 40,  # ~40/m -> ~120x100x100 = ~1200000
}


def compute_mesh_params(geometry: dict) -> dict:
    """Compute blockMesh parameters from geometry config.

    Returns dict with dim_x/y/z and nx/ny/nz cell counts.
    """
    dims = geometry["dimensions"]
    level = geometry.get("mesh_level", "M0")
    density = _MESH_DENSITY.get(level, _MESH_DENSITY["M0"])

    return {
        "dim_x": dims["x"],
        "dim_y": dims["y"],
        "dim_z": dims["z"],
        "nx": max(4, round(dims["x"] * density)),
        "ny": max(4, round(dims["y"] * density)),
        "nz": max(4, round(dims["z"] * density)),
    }


def compute_heater_params(boundary_conditions: dict, geometry: dict) -> dict:
    """Compute heater heat flux and related parameters.

    Returns dict with heat_flux (W/m2) and heater geometry.
    """
    heater = boundary_conditions.get("heater", {})
    power_kw = heater.get("power_kw", 9.0)
    width = heater.get("width", 0.5)
    height = heater.get("height", 0.5)

    # For Phase 1: heater is the entire heater_wall (x=0 face)
    # Heat flux distributed over that wall area
    wall_area = geometry["dimensions"]["y"] * geometry["dimensions"]["z"]
    heat_flux = (power_kw * 1000.0) / wall_area

    walls = boundary_conditions.get("walls", {})
    t_walls = walls.get("temperature", 293.15)

    return {
        "heat_flux": round(heat_flux, 2),
        "heater_width": width,
        "heater_height": height,
        "T_walls": t_walls,
        "T_initial": t_walls,
    }


def _build_probe_context(probes: list[dict]) -> list[dict]:
    """Convert YAML probe definitions to template context."""
    result = []
    for p in probes:
        pos = p["position"]
        result.append({
            "name": p["name"],
            "x": pos["x"],
            "y": pos["y"],
            "z": pos["z"],
        })
    return result


def render_templates(template_dir: Path, output_dir: Path, context: dict) -> None:
    """Render all .j2 templates into the output directory.

    Walks template_dir, renders each .j2 file with Jinja2,
    and writes the result to the corresponding path in output_dir
    (stripping the .j2 extension). Non-.j2 files are copied as-is.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )

    for template_path in template_dir.rglob("*"):
        if template_path.is_dir():
            continue

        rel = template_path.relative_to(template_dir)

        if template_path.suffix == ".j2":
            # Render Jinja2 template
            template = env.get_template(str(rel).replace("\\", "/"))
            rendered = template.render(**context)
            out_path = output_dir / rel.with_suffix("")  # strip .j2
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered, encoding="utf-8")
        else:
            # Copy non-template files as-is
            out_path = output_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_path, out_path)


def build_case(case_yaml: Path, output_dir: Path | None = None) -> Path:
    """Build an OpenFOAM case directory from a YAML definition.

    Args:
        case_yaml: Path to the YAML case definition file.
        output_dir: Output directory. Defaults to results/{case_name}/.

    Returns:
        Path to the created case directory.

    Raises:
        ValueError: If the YAML fails schema validation.
    """
    errors = load_and_validate(case_yaml)
    if errors:
        raise ValueError(f"Schema validation failed: {'; '.join(errors)}")

    data = load_yaml(case_yaml)
    case_name = data["case"]["name"]

    if output_dir is None:
        output_dir = _RESULTS_DIR / case_name

    # Clean and recreate output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Build template context
    mesh = compute_mesh_params(data["geometry"])
    heater = compute_heater_params(data["boundary_conditions"], data["geometry"])
    solver = data["solver"]
    probes = _build_probe_context(data.get("probes", []))

    context = {
        **mesh,
        **heater,
        "solver_name": solver["name"],
        "end_time": solver.get("end_time", 1000),
        "write_interval": solver.get("write_interval", 100),
        "probes": probes,
    }

    render_templates(_TEMPLATE_DIR, output_dir, context)
    return output_dir
