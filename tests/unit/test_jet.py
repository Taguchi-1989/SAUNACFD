"""Tests for free-jet centerline velocity decay (KPI K-05 physics)."""

from __future__ import annotations

from harness.jet import ROUND_JET_DECAY_CONST, free_jet_face_velocity


class TestFreeJet:
    def test_within_potential_core_equals_exit(self) -> None:
        # core length = K*d0 = 6.2*0.15 = 0.93 m; x=0.5 < core -> U_c == U0
        assert free_jet_face_velocity(2.0, 0.15, 0.5) == 2.0

    def test_continuous_at_core_end(self) -> None:
        d0 = 0.15
        core = ROUND_JET_DECAY_CONST * d0
        assert abs(free_jet_face_velocity(2.0, d0, core) - 2.0) < 1e-9

    def test_decays_beyond_core(self) -> None:
        # x=1.0 > core: U_c = 2.0 * 6.2*0.15/1.0 = 1.86
        assert abs(free_jet_face_velocity(2.0, 0.15, 1.0) - 1.86) < 1e-9

    def test_monotonic_decrease_with_distance(self) -> None:
        v1 = free_jet_face_velocity(2.0, 0.15, 1.0)
        v2 = free_jet_face_velocity(2.0, 0.15, 2.0)
        v3 = free_jet_face_velocity(2.0, 0.15, 4.0)
        assert v1 > v2 > v3

    def test_scales_with_exit_velocity(self) -> None:
        assert free_jet_face_velocity(4.0, 0.15, 2.0) == 2.0 * free_jet_face_velocity(2.0, 0.15, 2.0)

    def test_zero_or_negative_inputs(self) -> None:
        assert free_jet_face_velocity(0.0, 0.15, 1.0) == 0.0
        assert free_jet_face_velocity(2.0, 0.0, 1.0) == 0.0
        assert free_jet_face_velocity(2.0, 0.15, 0.0) == 0.0
        assert free_jet_face_velocity(2.0, 0.15, -1.0) == 0.0
