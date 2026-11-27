"""The hours a forecast covers fall on the UTC hour everywhere, half-hour time zones included."""
import numpy as np
import pandas as pd

from tahoe_snow import blend, pipeline


def test_newfoundlands_half_hour_clock_still_gives_hours_the_models_report_on():
    now = pd.Timestamp("2026-11-26 20:00")
    for tz in ("America/St_Johns", "America/Los_Angeles", "America/Toronto"):
        today = now.tz_localize("UTC").tz_convert(tz).tz_localize(None).normalize()
        hours = pipeline.forecast_hours(today, tz, now)
        assert (hours.minute == 0).all(), tz
        # Hourly figures on those hours make whole local days, today and every day after it but the last.
        days = blend.local_day_totals(pd.DataFrame({"snow_cm": np.ones(len(hours))}, index=hours), tz)["snow_cm"]
        assert days.loc[today] == 24, tz
        assert days.loc[today:].notna().sum() >= pipeline.DAYS - 1, tz
