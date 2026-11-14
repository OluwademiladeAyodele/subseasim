import math

import pytest

from app.core import units as u


def test_pressure_absolute_gauge_roundtrip():
    assert u.bara_to_pa(1.0) == 1.0e5
    assert u.pa_to_bara(250e5) == pytest.approx(250.0)
    # 0 barg is one standard atmosphere absolute
    assert u.barg_to_pa(0.0) == pytest.approx(101_325.0)
    assert u.pa_to_barg(u.bara_to_pa(100.0)) == pytest.approx(100.0 - 1.01325)
    for p in (0.5, 60.0, 380.0):
        assert u.pa_to_barg(u.barg_to_pa(p)) == pytest.approx(p)


def test_pressure_difference_has_no_reference_offset():
    assert u.bar_to_pa_delta(10.0) == 1.0e6
    assert u.pa_to_bar_delta(u.bara_to_pa(80) - u.bara_to_pa(60)) == pytest.approx(20.0)


def test_temperature():
    assert u.c_to_k(0.0) == 273.15
    assert u.k_to_c(u.c_to_k(95.0)) == pytest.approx(95.0)


def test_flow_and_productivity_index():
    assert u.m3d_to_m3s(86_400.0) == pytest.approx(1.0)
    assert u.m3s_to_m3d(u.m3d_to_m3s(1234.5)) == pytest.approx(1234.5)
    # 1 bbl = 0.158987294928 m3 exactly
    assert u.m3s_to_bbld(u.m3d_to_m3s(0.158987294928)) == pytest.approx(1.0)
    j = u.pi_m3d_per_bar_to_si(20.0)
    assert j == pytest.approx(20.0 / 86_400 / 1e5)
    assert u.pi_si_to_m3d_per_bar(j) == pytest.approx(20.0)


def test_viscosity():
    assert u.cp_to_pas(1.0) == 1.0e-3
    assert u.pas_to_cp(u.cp_to_pas(5.0)) == pytest.approx(5.0)


def test_kv_capacity_reproduces_kv_definition():
    """Kv definition: Q[m3/h] = Kv sqrt(dP[bar]/SG). Check via C sqrt(2 dP / rho)."""
    kv, dp_bar, rho = 50.0, 4.0, 850.0
    c = u.kv_to_capacity(kv)
    q_si = c * math.sqrt(2 * dp_bar * 1e5 / rho)
    q_expected_m3h = kv * math.sqrt(dp_bar / (rho / 1000.0))
    assert q_si * 3600.0 == pytest.approx(q_expected_m3h, rel=1e-12)


def test_cv_to_kv():
    assert u.cv_to_capacity(100.0) == pytest.approx(u.kv_to_capacity(86.5))


def test_loss_coefficient_capacity():
    d, k, rho, v = 0.1, 0.5, 900.0, 2.0
    c = u.loss_coefficient_to_capacity(k, d)
    area = math.pi * d * d / 4
    q = v * area
    dp_from_c = rho * q * q / (2 * c * c)
    assert dp_from_c == pytest.approx(k * rho * v * v / 2)
    with pytest.raises(ValueError):
        u.loss_coefficient_to_capacity(0.0, d)
