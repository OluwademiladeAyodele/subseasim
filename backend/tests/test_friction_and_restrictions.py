import math

import pytest

from app.simulation.hydraulics.friction import (
    churchill_friction_factor,
    colebrook_friction_factor,
    friction_pressure_drop,
)
from app.simulation.hydraulics.restriction import restriction_flow, restriction_pressure_drop
from app.simulation.valves.characteristics import relative_capacity


@pytest.mark.parametrize("re", [10.0, 100.0, 500.0, 1500.0])
def test_churchill_laminar_limit(re):
    assert churchill_friction_factor(re, 1e-4) == pytest.approx(64.0 / re, rel=1e-3)


@pytest.mark.parametrize("re", [1e4, 5e4, 1e5, 1e6])
@pytest.mark.parametrize("rr", [0.0, 1e-4, 1e-3])
def test_churchill_matches_colebrook_turbulent(re, rr):
    # Churchill (1977) reproduces Colebrook within a few percent in turbulent flow.
    assert churchill_friction_factor(re, rr) == pytest.approx(colebrook_friction_factor(re, rr), rel=0.03)


def test_churchill_continuous_through_transition():
    res = [1800 + 10 * i for i in range(300)]
    fs = [churchill_friction_factor(r, 1e-4) for r in res]
    jumps = [abs(fs[i + 1] - fs[i]) / fs[i] for i in range(len(fs) - 1)]
    assert max(jumps) < 0.02


def test_hagen_poiseuille_reference():
    """Laminar Darcy-Weisbach must reproduce dP = 128 mu L Q / (pi D^4)."""
    rho, mu, d, length = 900.0, 0.5, 0.05, 100.0
    q = 1e-4  # Re ~ 4.6
    expected = 128 * mu * length * q / (math.pi * d**4)
    assert friction_pressure_drop(q, rho, mu, d, length, 1e-5) == pytest.approx(expected, rel=1e-3)


def test_friction_is_odd_and_zero_at_zero_flow():
    args = (850.0, 0.005, 0.1, 1000.0, 4.5e-5)
    assert friction_pressure_drop(0.0, *args) == 0.0
    assert friction_pressure_drop(-0.01, *args) == pytest.approx(-friction_pressure_drop(0.01, *args))


def test_restriction_relation_inverse():
    rho, c = 850.0, 1e-3
    for q in (0.001, 0.01, -0.01):
        dp = restriction_pressure_drop(q, rho, c)
        assert restriction_flow(dp, rho, c) == pytest.approx(q)
    with pytest.raises(ValueError):
        restriction_pressure_drop(0.01, rho, 0.0)


@pytest.mark.parametrize("kind", ["linear", "quick_opening", "equal_percentage"])
def test_characteristics_endpoints_and_monotonic(kind):
    assert relative_capacity(kind, 0.0) == 0.0
    assert relative_capacity(kind, 1.0) == pytest.approx(1.0)
    xs = [i / 100 for i in range(101)]
    fs = [relative_capacity(kind, x) for x in xs]
    assert all(b > a for a, b in zip(fs, fs[1:]))
    with pytest.raises(ValueError):
        relative_capacity(kind, 1.2)


def test_equal_percentage_is_not_proportional():
    # 50 % travel gives much less than 50 % capacity with R = 30
    f = relative_capacity("equal_percentage", 0.5, 30.0)
    assert f == pytest.approx((30**0.5 - 1) / 29)
    assert f < 0.2
    # equal ratio for equal increments (away from x = 0)
    r1 = relative_capacity("equal_percentage", 0.6) + 1 / 29
    r2 = relative_capacity("equal_percentage", 0.8) + 1 / 29
    r3 = relative_capacity("equal_percentage", 1.0) + 1 / 29
    assert r2 / r1 == pytest.approx(r3 / r2)
