# SaunaFlow PoC Project Instructions

## Project Overview
SaunaFlow is a Python harness-driven CFD simulation tool for sauna thermal environments:
- OpenFOAM as computation engine (buoyantSimpleFoam / buoyantPimpleFoam)
- Python harness for case definition, execution control, KPI calculation, validation
- YAML/JSON declarative case definitions
- Experimental data comparison and validation reporting
- Target: Ubuntu Linux with OpenFOAM installed

## Architecture

```
src/
├── harness/            # Python orchestration layer
│   ├── cli.py          # CLI entry point
│   ├── schema.py       # YAML/JSON schema validation
│   ├── case_builder.py # Case definition → OpenFOAM directory
│   ├── mesh_runner.py  # Mesh generation execution
│   ├── solver_runner.py # Solver execution control
│   ├── probe_parser.py # Probe output parsing
│   ├── kpi.py          # KPI calculation (peak T, humidity, wind speed, arrival time)
│   ├── validation.py   # CFD vs experimental comparison
│   └── reporting.py    # Report generation (plots, tables, pass/fail)
├── templates/          # OpenFOAM case templates
│   └── base_case/      # Base OpenFOAM directory structure
└── utils/              # Shared utilities
```

```
configs/
├── cases/              # YAML case definitions
├── schemas/            # JSON Schema for validation
└── acceptance/         # Acceptance criteria definitions
```

```
experiments/
├── raw/                # Raw experimental CSV data
└── processed/          # Timestamp-aligned experimental data
```

## Development Rules

### Testing (Test Oracle)
- **ALWAYS run `pytest tests/ -x -q` before committing**
- Never commit code that breaks existing passing tests
- Every new feature MUST have tests
- Test hierarchy:
  1. `tests/unit/` - Schema validation, KPI calculation, CSV parsing
  2. `tests/integration/` - Full pipeline (build → mesh → run → parse → report)
  3. `tests/validation/` - CFD vs experimental data comparison

### Git Discipline
- Commit after each meaningful work unit
- Commit messages: what changed and why
- Push regularly for progress visibility
- **Always `git status` before committing** — verify staged changes are correct
- Pre-commit hooks (ruff, mypy, bandit) run automatically — if hook fails, fix and create NEW commit (never `--amend` after failure)
- **Use worktree per task** (`/worktree-task`): never mix unrelated changes on main
- One feature = one branch = one worktree

### Code Quality
- Python 3.11+, type hints where practical
- `src/` is the Python path root (use `from harness import ...`, not relative imports)
- File encoding: UTF-8 (always use `encoding="utf-8"` in `open()`)
- Keep imports absolute within src/

### Harness Architecture Principles
- **Harness is the boss** — OpenFOAM is just a compute engine
- All case configuration is declarative (YAML/JSON)
- Every execution is deterministic and reproducible from the same inputs
- Git manages all inputs; results are derived artifacts
- Solver is swappable — harness API stays the same

### OpenFOAM Integration
- Templates in `foam_templates/base_case/` — never hand-edit generated cases
- `case_builder.py` expands YAML → OpenFOAM directory structure
- Mesh levels: M0 (2D, 2-10万cells) → M1 (簡略3D, 10-50万) → M2 (PoC, 50-150万) → M3 (高精細, 150-300万)
- Start coarse, refine only after validation at current level

### KPI Definitions
- K-01: Steady-state temperature differential (upper/lower bench)
- K-02: Post-löyly peak temperature
- K-03: Post-löyly peak humidity
- K-04: Peak arrival time
- K-05: Face-level wind speed peak (Aufguss)
- K-06: Simplified thermal stress index
- K-07: Upper/lower relative difference

### Validation Tolerances (PoC Initial)
- Steady-state temperature: ±3-5°C at key probe points
- Post-löyly peak arrival time: ±5-10 seconds
- Wind speed peak: order-of-magnitude + direction match
- Upper/lower relative difference: trend match

## Success Criteria
1. All tests pass (`pytest tests/ -x -q` returns 0)
2. Dry sauna steady-state reproduces temperature stratification trend
3. Post-löyly temperature/humidity peak timing matches experimental trend
4. Aufguss wind speed differences are visible between conditions
5. YAML case swap → re-run produces comparable results

## Key Files
- `configs/cases/` - Case YAML definitions
- `configs/schemas/` - Input validation schemas
- `foam_templates/` - OpenFOAM template directories
- `experiments/` - Experimental measurement data
- `results/` - Generated results per case
- `docs/` - Documentation

## Phase Plan
1. **Phase 0**: Project foundation — repo, directory structure, YAML schema, CLI skeleton
2. **Phase 1**: Dry sauna steady-state — geometry, heater, probes, convergence
3. **Phase 2**: Löyly introduction — transient, vapor source, peak response
4. **Phase 3**: Aufguss introduction — jet/momentum source, local wind/heat
5. **Phase 4**: Experimental validation — sensor setup, CSV import, comparison
6. **Phase 5**: Comparison automation — batch comparison, auto-reporting
