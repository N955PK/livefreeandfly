"""Powder score: one transparent 0-10 number for how good the new snow should ski.

score = depth points x ratio factor x wind factor x layering factor x rain factor x timing factor
The same text is shown on the site's method page; change them together.
"""
from dataclasses import dataclass

import numpy as np

DEPTH_SCALE_IN = 6.0
FORMULA = [
    ("Depth points", "10 x (1 - exp(-new snow / 6 in)): 6 in gives 6.3, 12 in gives 8.6, 18 in gives 9.5."),
    ("Ratio factor", "0.55 at a snow ratio of 6:1 or less, rising to 1.0 at 12:1, flat to 20:1, 0.95 above."),
    ("Wind factor", "1.0 up to 15 mph ridge wind during and 12 h after the snow, falling to 0.6 at 45 mph."),
    ("Layering factor", "1.05 when the snow gets lighter through the storm (ratio up by 2 or more), "
                        "0.93 when it gets heavier by 2 or more, else 1.0."),
    ("Rain factor", "1 - 0.6 x the share of the storm's water that fell as rain here, "
                    "then x 0.6 if 2 mm or more of rain fell in the last 6 h."),
    ("Timing factor", "0.95 + 0.10 x the share of the snow that fell between 4 pm and 9 am."),
]


@dataclass
class DayPart:
    snow_in: float
    slr: float
    slr_change: float = 0.0
    ridge_wind_mph: float = 0.0
    rain_share: float = 0.0
    late_rain_mm: float = 0.0
    overnight_share: float = 0.5


def ratio_factor(slr: float) -> float:
    return float(np.interp(slr, [6.0, 12.0, 20.0, 20.01], [0.55, 1.0, 1.0, 0.95]))


def wind_factor(mph: float) -> float:
    return float(np.interp(mph, [15.0, 45.0], [1.0, 0.6]))


def layering_factor(slr_change: float) -> float:
    return 1.05 if slr_change >= 2.0 else 0.93 if slr_change <= -2.0 else 1.0


def rain_factor(rain_share: float, late_rain_mm: float) -> float:
    return (1.0 - 0.6 * float(np.clip(rain_share, 0.0, 1.0))) * (0.6 if late_rain_mm >= 2.0 else 1.0)


def score(part: DayPart) -> float:
    if not np.isfinite(part.snow_in) or part.snow_in <= 0 or not np.isfinite(part.slr):
        return 0.0
    depth = 10.0 * (1.0 - np.exp(-part.snow_in / DEPTH_SCALE_IN))
    timing = 0.95 + 0.10 * float(np.clip(part.overnight_share, 0.0, 1.0))
    value = (depth * ratio_factor(part.slr) * wind_factor(part.ridge_wind_mph) * layering_factor(part.slr_change)
             * rain_factor(part.rain_share, part.late_rain_mm) * timing)
    return float(np.clip(value, 0.0, 10.0))
