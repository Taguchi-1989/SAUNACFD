# 🧖 SaunaFlow — CFD-Driven Sauna Thermal Simulation

**Simulate the physics of sauna heat, löyly steam, and Aufguss airflow — from a zero-dimensional calculator to full 3D OpenFOAM CFD.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![OpenFOAM](https://img.shields.io/badge/OpenFOAM-v2312-red.svg)](https://openfoam.org)

🌐 **[Try the interactive Löyly Calculator →](https://taguchi-1989.github.io/SAUNAFEM/)**

---

## What is this?

A sauna is a deceptively complex thermal system. A 18 kW heater, wooden walls with non-trivial radiation view factors, buoyancy-driven stratification, transient steam from löyly, and the aerodynamic chaos of Aufguss — none of this is captured by simple rules of thumb.

**SaunaFlow** is a Python harness that turns declarative YAML case definitions into fully reproducible OpenFOAM simulations, computes sauna-specific KPIs, and compares results against experimental sensor data. It also ships standalone HTML tools so you can explore the physics without installing anything.

---

## Interactive Tools (no install needed)

| Tool | Description |
|------|-------------|
| [**Löyly Calculator**](https://taguchi-1989.github.io/SAUNAFEM/) | Zero-dimensional simulator: heat balance, Humidex body feel, latent/convective/radiant heat split, dependency graphs and sensitivity analysis |

---

## Key Results

Running 13 parametric CFD cases with `buoyantPimpleFoam`:

| Case | Heater Power | Upper Bench | Lower Bench | Target |
|------|-------------|-------------|-------------|--------|
| L-1  | 13 kW       | **95 °C**   | **54 °C**   | 80–100 / 40–60 °C ✅ |
| K-1  | 18 kW       | 102 °C      | 61 °C       | — |
| K-2  | 18 kW + vent | 88 °C      | 49 °C       | — |

> **Discovery**: `buoyantPimpleFoam` is essential for buoyancy-driven steady-state. `simpleFoam`-based solvers fail to converge even at 50,000 iterations.

---

## Architecture

```
YAML case definition
       │
       ▼
case_builder.py ──→ OpenFOAM directory (from foam_templates/)
       │
       ▼
solver_runner.py ──→ buoyantPimpleFoam / buoyantSimpleFoam
       │
       ▼
probe_parser.py ──→ time-series probe data
       │
       ▼
kpi.py ──→ K-01…K-07 (stratification, löyly peak, Aufguss wind, thermal stress)
       │
       ▼
validation.py + reporting.py ──→ Markdown / HTML report
```

All inputs are declarative. Swap a YAML file, re-run — results are fully reproducible.

---

## KPI Definitions

| KPI | Description |
|-----|-------------|
| K-01 | Steady-state temperature differential (upper/lower bench) |
| K-02 | Post-löyly peak temperature |
| K-03 | Post-löyly peak humidity |
| K-04 | Steam peak arrival time |
| K-05 | Face-level wind speed peak during Aufguss |
| K-06 | Simplified thermal stress index |
| K-07 | Upper/lower relative temperature difference |

---

## Quickstart

### Prerequisites
- Python 3.11+
- OpenFOAM v2312 (tested on Ubuntu; WSL2 on Windows works)

```bash
git clone https://github.com/Taguchi-1989/SAUNAFEM.git
cd SAUNAFEM
pip install -e .
```

### Run a case

```bash
# Build OpenFOAM case from YAML
PYTHONPATH=src python -m harness.cli build configs/cases/dry_sauna_steady.yaml

# Run solver (WSL2 example)
wsl -- /usr/bin/openfoam2312 bash scripts/run_openfoam_wsl.sh

# Generate report
PYTHONPATH=src python -m harness.cli report results/dry_sauna_steady/
```

### Run tests

```bash
pytest tests/ -x -q
```

---

## Physics Modeled

- **Buoyancy-driven stratification** — Boussinesq approximation, k-ε turbulence
- **Heater radiation** — view factor model between surfaces
- **Löyly steam** — transient vapor volume source with latent heat
- **Aufguss airflow** — momentum source (towel wave) with local convective enhancement
- **Skin heat transfer** — standalone 0D model: convection + radiation + evaporative cooling

---

## Parametric Study Coverage

29 YAML-defined cases covering:
- Heater power: 8–18 kW
- Löyly water volume: 0.1–0.5 L per throw
- Ventilation: none / natural / forced (pressure-outlet / fixed-value BC)
- Wall construction: spruce / cedar, 45–90 mm thickness
- Occupancy: empty / 2-person

---

## Project Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Repo, schema, CLI skeleton | ✅ Done |
| 1 | Dry sauna steady-state CFD | ✅ Done |
| 2 | Löyly transient simulation | ✅ Done |
| 3 | Aufguss (towel wave) | 🔄 In progress |
| 4 | Experimental validation (sensor data) | 📋 Planned |
| 5 | Auto batch comparison & reporting | 📋 Planned |

---

## Repository Structure

```
src/harness/        Python orchestration (CLI, builder, runner, KPI, reporting)
configs/cases/      29 YAML case definitions
foam_templates/     OpenFOAM case templates (never hand-edited)
tools/              Standalone HTML calculators
experiments/        Sensor data (raw + processed)
docs/               Governing equations, parametric study reports, field notes
firmware/           Sensor firmware for experimental setup
```

---

## Contributing

Issues and PRs welcome. If you're working on sauna thermal comfort, building physics, or OpenFOAM for HVAC applications, this is probably the most specific repo you'll find.

---

## Background

Built to answer a simple question: *why does the same sauna feel completely different depending on who's running it?* The answer is in the fluid dynamics.

---

*MIT License · Taguchi 1989*
