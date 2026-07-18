"""Mid-plane contour plots from an OpenFOAM case (any block topology).

Uses cell-centre coordinates (field "C", produced by
`postProcess -func writeCellCentres -time <t>`) so it works with the
multi-block heater meshes: cells in a slab around the z mid-plane are
selected and rendered with a triangulated contour.

Usage:
    python scripts/plot_contours.py <case_dir> <time> <out.png> [title]

If <time>/C is missing, run inside the case (WSL):
    postProcess -func writeCellCentres -time <time>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np


def _read_internal_field(path: Path) -> np.ndarray:
    """Parse an ascii volScalarField / volVectorField internalField."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"internalField\s+nonuniform\s+List<(scalar|vector)>\s*\n?\s*(\d+)\s*\n?\s*\(",
        text,
    )
    if m is None:
        raise ValueError(f"no nonuniform internalField found in {path}")
    kind, n = m.group(1), int(m.group(2))
    start = m.end()
    depth = 1
    i = start
    while depth > 0:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    body = text[start : i - 1]
    nums = np.fromstring(body.replace("(", " ").replace(")", " "), sep=" ")
    if kind == "vector":
        return nums.reshape(n, 3)
    return nums.reshape(n)


def plot_midplane(case_dir: Path, time: str, out: Path, title: str) -> None:
    tdir = case_dir / time
    centres = _read_internal_field(tdir / "C")
    temp = _read_internal_field(tdir / "T")
    vel = _read_internal_field(tdir / "U")

    z = centres[:, 2]
    zmid = 0.5 * (z.min() + z.max())
    dz = np.diff(np.unique(np.round(z, 6))).min()
    sel = np.abs(z - zmid) <= 0.51 * dz

    x, y = centres[sel, 0], centres[sel, 1]
    t_slice = temp[sel] - 273.15
    ux, uy = vel[sel, 0], vel[sel, 1]

    tri = mtri.Triangulation(x, y)

    fig, ax = plt.subplots(figsize=(9, 6.5))
    cf = ax.tricontourf(tri, t_slice, levels=24, cmap="inferno")
    fig.colorbar(cf, ax=ax, label="T [degC]")
    ax.quiver(x, y, ux, uy, color="white", scale_units="xy", angles="xy", width=0.003)
    umax = float(np.sqrt(ux**2 + uy**2).max())
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y (height) [m]")
    ax.set_title(f"{title}\nz mid-plane, t={time}s, |U|max={umax:.2f} m/s")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    case = Path(sys.argv[1])
    plot_midplane(
        case, sys.argv[2], Path(sys.argv[3]),
        sys.argv[4] if len(sys.argv) > 4 else case.name,
    )
