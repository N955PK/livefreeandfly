"""Seattle's passes sit below 850 hPa, so its forecast reads three lower levels; the Sierra's does not."""
import json

import numpy as np
import pandas as pd

from tahoe_snow import config, pipeline, usage
from tahoe_snow.config import MODELS, PRESSURE_LEVELS, REGIONS, RESORTS
from tahoe_snow.snow import features
from tahoe_snow.sources import openmeteo

HEIGHTS = {950: 540.0, 925: 760.0, 900: 990.0, 850: 1450.0, 800: 1950.0, 750: 2450.0, 700: 3000.0, 650: 3600.0,
           600: 4200.0, 550: 4850.0, 500: 5550.0}


def profile(levels, hours=48, t700=-8.0):
    """6.5 C/km through every level, anchored at 700 hPa = 3,000 m."""
    data = {"precipitation": np.full(hours, 1.0), "temperature_2m": np.full(hours, 0.0)}
    for level in levels:
        z = HEIGHTS[level]
        data[f"temperature_{level}hPa"] = np.full(hours, t700 - 6.5 * (z - 3000.0) / 1000.0)
        data[f"relative_humidity_{level}hPa"] = np.full(hours, 95.0)
        data[f"wind_speed_{level}hPa"] = np.full(hours, 36.0)
        data[f"geopotential_height_{level}hPa"] = np.full(hours, z)
    return pd.DataFrame(data, index=pd.date_range("2026-12-01", periods=hours, freq="h"))


def test_only_seattle_reads_below_850():
    assert config.levels_for("seattle") == [950, 925, 900] + PRESSURE_LEVELS
    for region in ("tahoe", "mammoth", "newengland"):
        assert config.levels_for(region) == PRESSURE_LEVELS, region


def test_the_sierra_asks_for_exactly_what_it_did():
    before = openmeteo.FORECAST_SURFACE_VARS + openmeteo.level_variables() + [openmeteo.WIND_DIRECTION]
    assert pipeline.forecast_variables("tahoe") == before
    assert pipeline.forecast_variables("mammoth") == before
    seattle = pipeline.forecast_variables("seattle")
    assert set(before) < set(seattle) and len(seattle) == len(before) + 12
    assert "temperature_925hPa" in seattle and "geopotential_height_950hPa" in seattle


def test_a_base_below_850_is_warmer_than_the_850_level():
    base_m = RESORTS["snoqualmie"].base_m
    held = features.hourly_features(profile(PRESSURE_LEVELS), base_m)
    read = features.hourly_features(profile(config.levels_for("seattle")), base_m)
    t850 = -8.0 - 6.5 * (1450.0 - 3000.0) / 1000.0
    assert abs(held["t0"].iloc[0] - t850) < 1e-9
    assert abs(read["t0"].iloc[0] - (t850 + 6.5 * (1450.0 - base_m) / 1000.0)) < 1e-6
    assert read["tw0"].iloc[0] > held["tw0"].iloc[0] + 3


def test_a_site_above_850_is_unchanged_by_the_lower_levels():
    for elev_m in (1500.0, 2450.0, RESORTS["rainier"].summit_m):
        held = features.hourly_features(profile(PRESSURE_LEVELS), elev_m)
        read = features.hourly_features(profile(config.levels_for("seattle")), elev_m)
        columns = [c for c in held.columns if c != "snow_level_m"]
        pd.testing.assert_frame_equal(held[columns], read[columns])


def test_a_low_level_a_model_only_half_reports_is_left_out():
    frame = profile(config.levels_for("seattle"))
    frame.loc[frame.index[30:], "temperature_925hPa"] = np.nan          # runs out before the forecast does
    frame["relative_humidity_950hPa"] = np.nan                           # never reported
    kept = pipeline.usable_levels(frame, "seattle")
    assert features.levels_in(kept) == [900] + PRESSURE_LEVELS
    whole = profile(config.levels_for("seattle"))
    assert features.levels_in(pipeline.usable_levels(whole, "seattle")) == config.levels_for("seattle")
    sierra = profile(PRESSURE_LEVELS)
    assert pipeline.usable_levels(sierra, "tahoe") is sierra


def test_the_extra_levels_are_counted_against_the_allowance():
    days = {"forecast_days": pipeline.DAYS, "past_days": pipeline.HISTORY_DAYS + 1}
    models = ",".join(config.DET_MODELS)

    def cost(region):
        return openmeteo.call_weight(openmeteo.FORECAST_URL, {
            "hourly": ",".join(pipeline.forecast_variables(region)), "models": models, **days})

    assert abs((cost("seattle") - cost("tahoe")) / 3 - usage.EXTRA_LEVEL_CALLS) < 0.01
    assert usage.resort_run_calls("tahoe") == usage.CALLS_PER_RESORT_RUN
    assert abs(usage.resort_run_calls("seattle") - (usage.CALLS_PER_RESORT_RUN + 3 * usage.EXTRA_LEVEL_CALLS)) < 1e-9
    seattle = {"seattle": REGIONS["seattle"]}
    assert round(usage.planned(seattle)) == round(13 * 2 * (51.9 + 3 * usage.EXTRA_LEVEL_CALLS))
    assert usage.estimate([], "seattle") == round(13 * usage.resort_run_calls("seattle"), 1)
    assert usage.planned() <= usage.PLAN_LIMIT


def test_seattle_blends_with_its_own_weights_and_the_rest_with_the_sierras():
    sierra = json.loads((MODELS / "weights.json").read_text())
    for region in ("tahoe", "mammoth", "newengland"):
        assert pipeline.load_weights(region) == sierra, region
    seattle = pipeline.load_weights("seattle")
    assert seattle == json.loads((MODELS / "weights_seattle.json").read_text())
    assert set(seattle) == set(config.DET_MODELS) and abs(sum(seattle.values()) - 1) < 0.005
