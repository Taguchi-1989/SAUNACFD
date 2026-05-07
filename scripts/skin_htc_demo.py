"""Sweep skin overall heat transfer coefficient over (T_air, RH, V).

Standalone driver for `harness.skin_htc`. Produces a CSV table and a
4-panel plot characterising "perceived heat" as a function of dry-bulb
temperature, relative humidity, and local air velocity.

Usage (from repo root):
    PYTHONPATH=src python scripts/skin_htc_demo.py
    PYTHONPATH=src python scripts/skin_htc_demo.py --t-mrt 110 --output-dir results/skin_htc

Outputs (under --output-dir, default results/skin_htc/):
    sweep.csv               flat table of every (T, RH, V) combination
    u_overall_vs_T_V.png    heat map: U_overall(T_air, V) at fixed RH
    q_total_vs_T_V.png      heat map: q_total(T_air, V) at fixed RH
    components_vs_V.png     line plot: q_conv, q_rad, q_evap vs V
    u_vs_RH.png             line plot: U_overall vs RH at fixed (T, V)
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from harness.skin_htc import BODY_PARTS, compute_skin_balance, sweep_grid

# Default sweep ranges spanning typical Finnish/Aufguss sauna conditions
DEFAULT_T_AIR = [60.0, 70.0, 80.0, 90.0, 100.0, 110.0]    # °C
DEFAULT_RH = [0.05, 0.10, 0.20, 0.30, 0.50, 0.80]          # -
DEFAULT_V = [0.1, 0.3, 0.5, 1.0, 1.5, 2.0, 3.0]            # m/s


def write_csv(rows: list[dict], path: Path) -> None:
    """Write sweep rows as CSV."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")


def plot_u_overall_heatmap(
    t_air: list[float],
    v_values: list[float],
    rh_fixed: float,
    t_mrt_c: float | None,
    out_path: Path,
) -> None:
    """Heat map of whole-body U_overall as a function of (T_air, V) at fixed RH."""
    grid = np.zeros((len(v_values), len(t_air)))
    for i, v in enumerate(v_values):
        for j, t in enumerate(t_air):
            bal = compute_skin_balance(t_air_c=t, rh=rh_fixed, v_local=v, t_mrt_c=t_mrt_c)
            grid[i, j] = bal.whole_body.u_overall

    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(
        grid,
        origin="lower",
        aspect="auto",
        extent=[min(t_air), max(t_air), min(v_values), max(v_values)],
        cmap="inferno",
    )
    ax.set_xlabel("T_air [°C]")
    ax.set_ylabel("V_local [m/s]")
    ax.set_title(f"Whole-body U_overall  (RH={rh_fixed:.0%})")
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("U_overall [W/(m²·K)]")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"  wrote {out_path}")


def plot_q_total_heatmap(
    t_air: list[float],
    v_values: list[float],
    rh_fixed: float,
    t_mrt_c: float | None,
    out_path: Path,
) -> None:
    """Heat map of whole-body q_total as a function of (T_air, V) at fixed RH."""
    grid = np.zeros((len(v_values), len(t_air)))
    for i, v in enumerate(v_values):
        for j, t in enumerate(t_air):
            bal = compute_skin_balance(t_air_c=t, rh=rh_fixed, v_local=v, t_mrt_c=t_mrt_c)
            grid[i, j] = bal.whole_body.q_total

    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(
        grid,
        origin="lower",
        aspect="auto",
        extent=[min(t_air), max(t_air), min(v_values), max(v_values)],
        cmap="hot",
    )
    ax.set_xlabel("T_air [°C]")
    ax.set_ylabel("V_local [m/s]")
    ax.set_title(f"Whole-body q_total  (RH={rh_fixed:.0%})")
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("q_total [W/m²]")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"  wrote {out_path}")


def plot_components_vs_velocity(
    t_air_fixed: float,
    rh_fixed: float,
    t_mrt_c: float | None,
    out_path: Path,
) -> None:
    """Line plot of q_conv, q_rad, q_evap, q_total vs V at fixed (T, RH)."""
    v_values = np.linspace(0.05, 3.0, 60)
    q_conv, q_rad, q_evap, q_total = [], [], [], []
    for v in v_values:
        bal = compute_skin_balance(
            t_air_c=t_air_fixed, rh=rh_fixed, v_local=float(v), t_mrt_c=t_mrt_c,
        )
        wb = bal.whole_body
        q_conv.append(wb.q_conv)
        q_rad.append(wb.q_rad)
        q_evap.append(wb.q_evap)
        q_total.append(wb.q_total)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(v_values, q_conv, label="q_conv (convection)")
    ax.plot(v_values, q_rad, label="q_rad (radiation)", linestyle="--")
    ax.plot(v_values, q_evap, label="q_evap (evap/cond)", linestyle=":")
    ax.plot(v_values, q_total, label="q_total", color="black", linewidth=2)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.set_xlabel("V_local [m/s]")
    ax.set_ylabel("Heat flux [W/m²]")
    ax.set_title(
        f"Skin heat flux components  (T_air={t_air_fixed:.0f}°C, RH={rh_fixed:.0%})"
    )
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"  wrote {out_path}")


def plot_u_vs_rh(
    t_air_fixed: float,
    v_values: list[float],
    t_mrt_c: float | None,
    out_path: Path,
) -> None:
    """U_overall vs RH at several velocities, fixed T_air."""
    rh_values = np.linspace(0.0, 0.95, 50)
    fig, ax = plt.subplots(figsize=(8, 5))
    for v in v_values:
        u_arr = []
        for rh in rh_values:
            bal = compute_skin_balance(
                t_air_c=t_air_fixed, rh=float(rh), v_local=v, t_mrt_c=t_mrt_c,
            )
            u_arr.append(bal.whole_body.u_overall)
        ax.plot(rh_values, u_arr, label=f"V = {v:.1f} m/s")
    ax.set_xlabel("Relative humidity [-]")
    ax.set_ylabel("U_overall [W/(m²·K)]")
    ax.set_title(f"Whole-body U_overall vs RH  (T_air={t_air_fixed:.0f}°C)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"  wrote {out_path}")


def print_summary_table(t_mrt_c: float | None) -> None:
    """Print a small comparison table for a few canonical sauna scenarios."""
    scenarios = [
        ("Mild dry, calm",      70.0, 0.10, 0.10),
        ("Hot dry, calm",       90.0, 0.05, 0.10),
        ("Hot dry, Aufguss",    90.0, 0.05, 2.00),
        ("Löyly humid, calm",   85.0, 0.50, 0.20),
        ("Löyly humid, Aufguss",85.0, 0.50, 2.00),
        ("Extreme",            105.0, 0.30, 2.50),
    ]
    print()
    print("Scenario summary (whole body):")
    header = (
        f"  {'name':<22}{'T':>6}{'RH':>6}{'V':>6}"
        f"{'h_c':>8}{'h_r':>8}{'q_c':>9}{'q_r':>9}{'q_e':>9}{'q_tot':>9}{'U_ov':>9}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for name, t_air, rh, v in scenarios:
        bal = compute_skin_balance(t_air_c=t_air, rh=rh, v_local=v, t_mrt_c=t_mrt_c)
        wb = bal.whole_body
        u_str = f"{wb.u_overall:>9.2f}" if not np.isnan(wb.u_overall) else "      nan"
        print(
            f"  {name:<22}{t_air:>6.0f}{rh:>6.2f}{v:>6.2f}"
            f"{wb.h_conv:>8.2f}{wb.h_rad:>8.2f}"
            f"{wb.q_conv:>9.0f}{wb.q_rad:>9.0f}{wb.q_evap:>9.0f}"
            f"{wb.q_total:>9.0f}{u_str}"
        )
    print()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--t-mrt", type=float, default=None,
                   help="Mean radiant temperature [°C]. Default: T_air per row.")
    p.add_argument("--t-skin", type=float, default=36.0, help="Skin temperature [°C].")
    p.add_argument("--w-skin", type=float, default=0.4, help="Skin wettedness [0-1].")
    p.add_argument("--output-dir", type=Path, default=Path("results/skin_htc"))
    p.add_argument("--rh-for-heatmap", type=float, default=0.30,
                   help="RH at which to render U/q heat maps.")
    p.add_argument("--t-for-components", type=float, default=90.0,
                   help="T_air [°C] for components-vs-V plot.")
    p.add_argument("--rh-for-components", type=float, default=0.30,
                   help="RH for components-vs-V plot.")
    p.add_argument("--t-for-rh-curve", type=float, default=85.0,
                   help="T_air [°C] for U-vs-RH plot.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Writing outputs to {out_dir}/")

    rows = sweep_grid(
        t_air_c_values=DEFAULT_T_AIR,
        rh_values=DEFAULT_RH,
        v_values=DEFAULT_V,
        t_mrt_c=args.t_mrt,
        t_skin_c=args.t_skin,
        w_skin=args.w_skin,
        parts=BODY_PARTS,
    )
    write_csv(rows, out_dir / "sweep.csv")

    plot_u_overall_heatmap(
        DEFAULT_T_AIR, DEFAULT_V, args.rh_for_heatmap, args.t_mrt,
        out_dir / "u_overall_vs_T_V.png",
    )
    plot_q_total_heatmap(
        DEFAULT_T_AIR, DEFAULT_V, args.rh_for_heatmap, args.t_mrt,
        out_dir / "q_total_vs_T_V.png",
    )
    plot_components_vs_velocity(
        args.t_for_components, args.rh_for_components, args.t_mrt,
        out_dir / "components_vs_V.png",
    )
    plot_u_vs_rh(
        args.t_for_rh_curve, [0.1, 0.5, 1.0, 2.0], args.t_mrt,
        out_dir / "u_vs_RH.png",
    )

    print_summary_table(args.t_mrt)


if __name__ == "__main__":
    main()
