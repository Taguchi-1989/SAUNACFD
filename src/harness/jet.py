"""Turbulent free-jet centerline velocity decay.

Used to turn an Aufguss source (a fan/towel-driven air movement with a physical
exit velocity and source size) into a predicted face-level wind speed at a given
distance — instead of rescaling an abstract mixing coefficient (review item C6,
KPI K-05).

Round turbulent free jet (Rajaratnam 1976; Tollmien similarity):
  - A potential core of length x_c ≈ K · d0 where the centerline velocity equals
    the exit velocity U0.
  - Beyond the core the centerline velocity decays as
      U_c / U0 = K · d0 / x        (x > x_c)
    which is continuous with the core (U_c = U0 at x = x_c).

K ≈ 6.2 is the standard round-jet decay constant. This is a steady-jet
idealisation of an inherently unsteady waft, so treat it as an engineering
estimate, not a validated prediction.
"""

from __future__ import annotations

ROUND_JET_DECAY_CONST = 6.2  # K: centerline decay constant for a round jet


def free_jet_face_velocity(
    exit_velocity: float,
    source_diameter: float,
    distance: float,
    decay_const: float = ROUND_JET_DECAY_CONST,
) -> float:
    """Centerline velocity of a round turbulent free jet at ``distance`` [m/s].

    Args:
        exit_velocity: Jet velocity at the source U0 [m/s].
        source_diameter: Characteristic source diameter d0 [m].
        distance: Distance from the source to the target (face) [m].
        decay_const: Round-jet decay constant K (default 6.2).

    Returns:
        Centerline (face) velocity [m/s]. Returns 0.0 for non-positive inputs.
        Within the potential core (distance <= K·d0) it equals exit_velocity;
        beyond it, it decays as K·d0/distance.
    """
    if exit_velocity <= 0.0 or source_diameter <= 0.0 or distance <= 0.0:
        return 0.0
    core_length = decay_const * source_diameter
    if distance <= core_length:
        return exit_velocity
    return exit_velocity * decay_const * source_diameter / distance
