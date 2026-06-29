"""Tests for grid-convergence (Richardson/GCI) analysis."""

from __future__ import annotations

import math

import pytest

from harness.grid_convergence import (
    GridLevel,
    gci_report_markdown,
    three_grid_gci,
)


def _levels(v_coarse, v_med, v_fine, n=(8000, 64000, 512000)):
    return (
        GridLevel("M0", n[0], v_coarse),
        GridLevel("M1", n[1], v_med),
        GridLevel("M2", n[2], v_fine),
    )


class TestThreeGridGCI:
    def test_second_order_monotonic_convergence(self) -> None:
        # Construct values consistent with p≈2 on a fixed refinement ratio r=2
        # (cell counts 8k/64k/512k -> h ratio 2). phi = phi_ext + C*h^2.
        # h_fine=1, h_med=2, h_coarse=4 (relative); phi_ext=100, C=1.
        # fine=101, med=104, coarse=116.
        coarse, med, fine = _levels(116.0, 104.0, 101.0)
        res = three_grid_gci(coarse, med, fine)
        assert abs(res.observed_order_p - 2.0) < 0.1
        assert abs(res.extrapolated_value - 100.0) < 0.5
        assert res.gci_fine_pct > 0.0
        assert res.gci_fine_pct < res.gci_medium_pct  # finer grid => smaller error
        assert res.in_asymptotic_range

    def test_extrapolated_between_or_beyond_fine(self) -> None:
        coarse, med, fine = _levels(116.0, 104.0, 101.0)
        res = three_grid_gci(coarse, med, fine)
        # Extrapolated value should be closer to fine than coarse is
        assert abs(res.extrapolated_value - 101.0) < abs(116.0 - 101.0)

    def test_identical_solutions_mesh_independent(self) -> None:
        coarse, med, fine = _levels(95.0, 95.0, 95.0)
        res = three_grid_gci(coarse, med, fine)
        assert res.gci_fine_pct == 0.0
        assert res.in_asymptotic_range
        assert res.extrapolated_value == 95.0

    def test_partial_convergence_fine_equals_medium(self) -> None:
        """fine==medium but coarse differs must not crash (order unresolved)."""
        coarse, med, fine = _levels(116.0, 101.0, 101.0)
        res = three_grid_gci(coarse, med, fine)
        assert math.isnan(res.observed_order_p)
        assert res.extrapolated_value == 101.0
        assert not res.in_asymptotic_range
        assert res.note is not None and "unresolved" in res.note
        assert res.gci_fine_pct == 0.0  # fine and medium agree

    def test_partial_convergence_medium_equals_coarse(self) -> None:
        """medium==coarse but fine differs must not crash (order unresolved)."""
        coarse, med, fine = _levels(104.0, 104.0, 101.0)
        res = three_grid_gci(coarse, med, fine)
        assert math.isnan(res.observed_order_p)
        assert res.extrapolated_value == 101.0
        assert not res.in_asymptotic_range
        assert res.gci_medium_pct == 0.0  # medium and coarse agree
        assert res.gci_fine_pct > 0.0     # fine moved

    def test_requires_ordered_grids(self) -> None:
        bad_fine = GridLevel("M2", 1000, 101.0)  # fewer cells than medium
        med = GridLevel("M1", 64000, 104.0)
        coarse = GridLevel("M0", 8000, 116.0)
        with pytest.raises(ValueError):
            three_grid_gci(coarse, med, bad_fine)

    def test_report_renders(self) -> None:
        coarse, med, fine = _levels(116.0, 104.0, 101.0)
        res = three_grid_gci(coarse, med, fine)
        md = gci_report_markdown(res, quantity="upper_bench T")
        assert "Grid convergence" in md
        assert "Observed order" in md or "order" in md
