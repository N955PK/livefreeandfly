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


def test_a_region_moved_to_another_collector_does_not_leave_its_old_forecast_behind(tmp_path, monkeypatch):
    # The Tetons moved from the first collector to the fifth; the file left on the first one's branch was read by
    # phones for a day as if it were current.
    (tmp_path / "forecast").mkdir()
    for name in ("tahoe", "tetons_was_here"):
        (tmp_path / "forecast" / f"{name}.json").write_text("{}")
    monkeypatch.setattr(pipeline, "DATA", tmp_path)
    monkeypatch.setattr(pipeline, "REGIONS", {"tahoe": object()})
    assert pipeline.drop_moved_forecasts() == ["tetons_was_here"]
    assert [p.name for p in (tmp_path / "forecast").iterdir()] == ["tahoe.json"]
