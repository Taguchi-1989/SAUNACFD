"""Grid-convergence analysis (Richardson extrapolation, Roache GCI).

Quantifies the discretisation (mesh) error of the OpenFOAM results so the
project can stop reporting a single coarse-mesh number as if it were
mesh-independent (review item C8).

This module does NOT run OpenFOAM. The mesh studies (M0 -> M1 -> M2) are run in
the WSL/OpenFOAM environment; this consumes the resulting probe values (one
scalar per grid level) and reports:

  - observed order of convergence p,
  - the Richardson-extrapolated (h -> 0) value,
  - the Grid Convergence Index (GCI) error bands,
  - whether the solutions are in the asymptotic range.

References:
  - Roache (1994), "Perspective: A Method for Uniform Reporting of Grid
    Refinement Studies", J. Fluids Eng. 116:405-413.
  - Celik et al. (2008), ASME J. Fluids Eng. 130:078001 (GCI procedure).
"""

from __future__ import annotations

from dataclasses import dataclass

import math


@dataclass
class GridLevel:
    """One mesh level in a refinement study."""

    name: str           # e.g. "M0", "M1", "M2"
    cell_count: int     # number of cells
    value: float        # solution value at the monitored point (e.g. probe T [K])

    @property
    def h(self) -> float:
        """Representative cell size (relative). h ∝ N^(-1/3) for 3D meshes."""
        return self.cell_count ** (-1.0 / 3.0)


@dataclass
class GridConvergenceResult:
    """Result of a three-grid convergence study."""

    observed_order_p: float          # observed order of accuracy
    extrapolated_value: float        # Richardson extrapolation to h -> 0
    gci_fine_pct: float              # GCI between fine and medium grids [%]
    gci_medium_pct: float            # GCI between medium and coarse grids [%]
    asymptotic_ratio: float          # ~1.0 => solutions are in the asymptotic range
    in_asymptotic_range: bool        # |ratio - 1| < 0.1
    refinement_ratios: tuple[float, float]  # (r21, r32)
    note: str | None = None


def _refinement_ratio(fine: GridLevel, coarse: GridLevel) -> float:
    """Refinement ratio r = h_coarse / h_fine (>1)."""
    return coarse.h / fine.h


def three_grid_gci(
    coarse: GridLevel,
    medium: GridLevel,
    fine: GridLevel,
    safety_factor: float = 1.25,
) -> GridConvergenceResult:
    """Three-grid Richardson / GCI analysis (Celik et al. 2008 procedure).

    Args:
        coarse, medium, fine: the three grid levels, fine = most cells.
        safety_factor: Fs in the GCI formula (1.25 for 3+ grids, Roache).

    Returns:
        GridConvergenceResult with order, extrapolated value, and GCI bands.

    Raises:
        ValueError: if the grids are not strictly ordered by cell count or the
            refinement ratios are too close to 1 to resolve an order.
    """
    if not (fine.cell_count > medium.cell_count > coarse.cell_count):
        raise ValueError("grids must satisfy fine > medium > coarse in cell_count")

    # Solutions: 1 = fine, 2 = medium, 3 = coarse (Celik notation)
    phi1, phi2, phi3 = fine.value, medium.value, coarse.value
    r21 = _refinement_ratio(fine, medium)
    r32 = _refinement_ratio(medium, coarse)

    if r21 <= 1.0 + 1e-6 or r32 <= 1.0 + 1e-6:
        raise ValueError("refinement ratios must exceed 1 (distinct mesh sizes)")

    eps32 = phi3 - phi2
    eps21 = phi2 - phi1

    # Degenerate case: no change between grids -> already mesh-independent.
    # Raw relative differences (used for both the GCI and the degenerate guards).
    e21a = abs((phi1 - phi2) / phi1) if phi1 != 0 else abs(phi1 - phi2)
    e32a = abs((phi2 - phi3) / phi2) if phi2 != 0 else abs(phi2 - phi3)

    if abs(eps21) < 1e-12 and abs(eps32) < 1e-12:
        return GridConvergenceResult(
            observed_order_p=float("nan"),
            extrapolated_value=phi1,
            gci_fine_pct=0.0,
            gci_medium_pct=0.0,
            asymptotic_ratio=1.0,
            in_asymptotic_range=True,
            refinement_ratios=(r21, r32),
            note="solutions identical across grids — already mesh-independent",
        )

    # Partial convergence: exactly one grid pair is identical while the third
    # differs (e.g. fine==medium but coarse moved, or medium==coarse but fine
    # moved). The observed order p is then undefined — solving for it divides by
    # zero / takes log(0). This is a real mesh-study outcome, so report it
    # cleanly: no order, fine value as best estimate, and the raw relative
    # differences as a conservative (non-Richardson) error proxy.
    if abs(eps21) < 1e-12 or abs(eps32) < 1e-12:
        return GridConvergenceResult(
            observed_order_p=float("nan"),
            extrapolated_value=phi1,
            gci_fine_pct=e21a * 100.0,
            gci_medium_pct=e32a * 100.0,
            asymptotic_ratio=float("nan"),
            in_asymptotic_range=False,
            refinement_ratios=(r21, r32),
            note=(
                "order unresolved: one grid pair is identical (partial "
                "convergence). GCI shown is the raw relative difference, not a "
                "Richardson estimate — refine further to resolve the order."
            ),
        )

    s = math.copysign(1.0, eps32 / eps21) if eps21 != 0 else 1.0

    # Solve for observed order p by fixed-point iteration (Celik eq. 3).
    # p = (1/ln(r21)) * |ln|eps32/eps21| + q(p)| ;  q(p) = ln((r21^p - s)/(r32^p - s))
    p = 2.0
    for _ in range(100):
        if r21 == r32:
            q = 0.0
        else:
            q = math.log((r21**p - s) / (r32**p - s))
        ratio = abs(eps32 / eps21) if eps21 != 0 else 1.0
        p_new = abs(math.log(ratio) + q) / math.log(r21)
        if abs(p_new - p) < 1e-6:
            p = p_new
            break
        p = p_new

    # Richardson extrapolation of the fine-grid solution to h -> 0.
    phi_ext = (r21**p * phi1 - phi2) / (r21**p - 1.0)

    # Grid Convergence Index (relative form); e21a/e32a computed above.
    gci_fine = safety_factor * e21a / (r21**p - 1.0) * 100.0
    gci_medium = safety_factor * e32a / (r32**p - 1.0) * 100.0

    # Asymptotic range check: GCI_medium / (r21^p * GCI_fine) ~ 1.0
    denom = (r21**p) * gci_fine
    asymptotic_ratio = gci_medium / denom if denom != 0 else float("nan")
    in_range = abs(asymptotic_ratio - 1.0) < 0.10

    return GridConvergenceResult(
        observed_order_p=p,
        extrapolated_value=phi_ext,
        gci_fine_pct=gci_fine,
        gci_medium_pct=gci_medium,
        asymptotic_ratio=asymptotic_ratio,
        in_asymptotic_range=in_range,
        refinement_ratios=(r21, r32),
        note=None if in_range else "not in asymptotic range — refine further before trusting p",
    )


def gci_report_markdown(result: GridConvergenceResult, quantity: str = "value") -> str:
    """Render a grid-convergence result as a short Markdown block."""
    p = result.observed_order_p
    lines = [
        f"### Grid convergence — {quantity}",
        "",
        f"- Observed order of accuracy *p*: **{p:.2f}**" if p == p else "- Observed order *p*: n/a",
        f"- Richardson-extrapolated (h→0): **{result.extrapolated_value:.2f}**",
        f"- GCI (fine→medium): **{result.gci_fine_pct:.2f}%**",
        f"- GCI (medium→coarse): {result.gci_medium_pct:.2f}%",
        f"- Refinement ratios (r21, r32): {result.refinement_ratios[0]:.2f}, {result.refinement_ratios[1]:.2f}",
        f"- Asymptotic range: {'yes' if result.in_asymptotic_range else 'NO'} "
        f"(ratio {result.asymptotic_ratio:.3f})",
    ]
    if result.note:
        lines.append(f"- Note: {result.note}")
    lines.append("")
    return "\n".join(lines)
