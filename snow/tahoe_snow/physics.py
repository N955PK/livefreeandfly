"""Moist thermodynamics and profile helpers. Temperatures in deg C, pressure in hPa, heights in m."""
import numpy as np

EPS = 0.622
CP = 1005.0
LV = 2.501e6


def sat_vapor_pressure_hpa(t_c):
    """Saturation vapor pressure over water (Bolton 1980)."""
    t_c = np.asarray(t_c, dtype=float)
    return 6.112 * np.exp(17.67 * t_c / (t_c + 243.5))


def mixing_ratio(e_hpa, p_hpa):
    return EPS * e_hpa / (p_hpa - e_hpa)


def rh_from_specific_humidity(q_kgkg, t_c, p_hpa):
    q = np.asarray(q_kgkg, dtype=float)
    e = q * p_hpa / (EPS + (1 - EPS) * q)
    return np.clip(100.0 * e / sat_vapor_pressure_hpa(t_c), 0.0, 100.0)


def wet_bulb_c(t_c, rh_pct, p_hpa, iterations: int = 30):
    """Isobaric wet-bulb temperature by bisection on the psychrometric balance.

    Valid at mountain pressures, unlike sea-level empirical fits.
    """
    t_c, rh_pct, p_hpa = np.broadcast_arrays(np.asarray(t_c, float), np.asarray(rh_pct, float),
                                             np.asarray(p_hpa, float))
    w = mixing_ratio(np.clip(rh_pct, 0, 100) / 100.0 * sat_vapor_pressure_hpa(t_c), p_hpa)
    lo = t_c - 40.0
    hi = t_c.copy()
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        ws = mixing_ratio(sat_vapor_pressure_hpa(mid), p_hpa)
        # Positive residual: mid is too warm to be the wet-bulb.
        residual = CP * (mid - t_c) + LV * (ws - w)
        hi = np.where(residual > 0, mid, hi)
        lo = np.where(residual > 0, lo, mid)
    out = 0.5 * (lo + hi)
    return np.where(np.isnan(t_c) | np.isnan(rh_pct), np.nan, out)


def interp_profile(heights_m, values, target_m):
    """Linear interpolation in height along the last axis; ends are held constant.

    ``heights_m`` and ``values`` have shape (..., n_levels) in any vertical order.
    """
    heights_m = np.asarray(heights_m, float)
    values = np.asarray(values, float)
    order = np.argsort(heights_m, axis=-1)
    h = np.take_along_axis(heights_m, order, axis=-1)
    v = np.take_along_axis(values, order, axis=-1)
    target = np.broadcast_to(np.asarray(target_m, float), h.shape[:-1])[..., None]
    idx = np.clip((h < target).sum(axis=-1, keepdims=True), 1, h.shape[-1] - 1)
    h0 = np.take_along_axis(h, idx - 1, axis=-1)
    h1 = np.take_along_axis(h, idx, axis=-1)
    v0 = np.take_along_axis(v, idx - 1, axis=-1)
    v1 = np.take_along_axis(v, idx, axis=-1)
    frac = np.clip((target - h0) / np.where(h1 == h0, 1.0, h1 - h0), 0.0, 1.0)
    return (v0 + frac * (v1 - v0))[..., 0]


def snow_level_m(heights_m, wet_bulb, threshold_c: float = 0.5):
    """Height where wet-bulb falls to ``threshold_c``, searching from the top down.

    Returns the height of the highest crossing: below it the column first becomes
    warmer than the threshold. If the whole column is colder, returns the lowest
    level height; if the whole column is warmer, returns the top level height.
    """
    heights_m = np.atleast_2d(np.asarray(heights_m, float))
    wet_bulb = np.atleast_2d(np.asarray(wet_bulb, float))
    order = np.argsort(-heights_m, axis=-1)
    h = np.take_along_axis(heights_m, order, axis=-1)
    tw = np.take_along_axis(wet_bulb, order, axis=-1)
    out = np.full(h.shape[0], np.nan)
    for i in range(h.shape[0]):
        if np.isnan(tw[i]).all():
            continue
        warm = tw[i] > threshold_c
        if warm[0]:
            out[i] = h[i, 0]
        elif not warm.any():
            out[i] = h[i, -1]
        else:
            k = int(np.argmax(warm))
            frac = (threshold_c - tw[i, k - 1]) / (tw[i, k] - tw[i, k - 1])
            out[i] = h[i, k - 1] + frac * (h[i, k] - h[i, k - 1])
    return out


def kuchera_slr(tmax_k):
    """Kuchera snow-to-liquid ratio from the warmest temperature below 500 hPa (K)."""
    tmax_k = np.asarray(tmax_k, dtype=float)
    return np.where(tmax_k > 271.16, 12.0 + 2.0 * (271.16 - tmax_k), 12.0 + (271.16 - tmax_k))
