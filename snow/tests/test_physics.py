import numpy as np

from tahoe_snow import physics


def test_wet_bulb_equals_temperature_when_saturated():
    assert abs(physics.wet_bulb_c(-3.0, 100.0, 700.0) - (-3.0)) < 0.01


def test_wet_bulb_dry_air_at_700hpa():
    tw = float(physics.wet_bulb_c(0.0, 50.0, 700.0))
    assert -5.0 < tw < -3.0


def test_wet_bulb_propagates_nan():
    assert np.isnan(physics.wet_bulb_c(np.nan, 50.0, 700.0))


def test_rh_from_specific_humidity_saturated():
    es = physics.sat_vapor_pressure_hpa(-5.0)
    q = 0.622 * es / (700.0 - 0.378 * es)
    assert abs(physics.rh_from_specific_humidity(q, -5.0, 700.0) - 100.0) < 0.5


def test_interp_profile_midpoint_and_clamp():
    h = np.array([[3000.0, 1500.0]])
    v = np.array([[-10.0, 0.0]])
    assert abs(physics.interp_profile(h, v, 2250.0)[0] - (-5.0)) < 1e-9
    assert physics.interp_profile(h, v, 1000.0)[0] == 0.0
    assert physics.interp_profile(h, v, 4000.0)[0] == -10.0


def test_snow_level_interpolates():
    level = physics.snow_level_m([1500.0, 3000.0], [3.5, -2.5], threshold_c=0.5)
    assert abs(level[0] - 2250.0) < 1e-6


def test_snow_level_takes_highest_crossing_with_inversion():
    level = physics.snow_level_m([1000.0, 2000.0, 3000.0, 4000.0], [-1.0, 2.0, 1.0, -5.0])
    assert 3000.0 < level[0] < 4000.0


def test_snow_level_all_cold_and_all_warm():
    assert physics.snow_level_m([1500.0, 3000.0], [-4.0, -9.0])[0] == 1500.0
    assert physics.snow_level_m([1500.0, 3000.0], [6.0, 2.0])[0] == 3000.0


def test_kuchera_reference_values():
    assert abs(physics.kuchera_slr(271.16) - 12.0) < 1e-9
    assert abs(physics.kuchera_slr(261.16) - 22.0) < 1e-9
    assert abs(physics.kuchera_slr(272.16) - 10.0) < 1e-9
