"""Seattle's passes and all of New England sit below 850 hPa, so their forecasts read lower levels; the Sierra's
does not."""
import json

import numpy as np
import pandas as pd

from tahoe_snow import config, pipeline, usage
from tahoe_snow.config import MODELS, PRESSURE_LEVELS, REGIONS, RESORTS
from tahoe_snow.snow import dataset, features, phase, train
from tahoe_snow.sources import omfiles_s3, openmeteo

HEIGHTS = {1000: 110.0, 975: 320.0, 950: 540.0, 925: 760.0, 900: 990.0, 850: 1450.0, 800: 1950.0, 750: 2450.0,
           700: 3000.0, 650: 3600.0, 600: 4200.0, 550: 4850.0, 500: 5550.0}


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


def test_only_the_low_regions_read_below_850():
    assert config.levels_for("seattle") == [950, 925, 900] + PRESSURE_LEVELS
    assert config.levels_for("newengland") == [1000, 975, 950, 925, 900] + PRESSURE_LEVELS
    for region in ("tahoe", "mammoth"):
        assert config.levels_for(region) == PRESSURE_LEVELS, region


def test_every_new_england_height_is_inside_the_levels_it_reads():
    # Before, every lift-served foot of New England was under the lowest level read and got its temperature.
    lowest, floor_850 = HEIGHTS[min(config.levels_for("newengland"), key=HEIGHTS.get)], HEIGHTS[850]
    lifts = [r for r in config.resorts_in("newengland") if r.kind == "resort"]
    assert all(r.summit_m < floor_850 for r in lifts)
    # Attitash's base, the lowest, is 73 m above the 1000 hPa level of a standard day.
    assert min(r.base_m for r in lifts) > lowest
    attitash = RESORTS["attitash"]
    held = features.hourly_features(profile(PRESSURE_LEVELS), attitash.base_m)
    read = features.hourly_features(profile(config.levels_for("newengland")), attitash.base_m)
    assert abs(read["t0"].iloc[0] - held["t0"].iloc[0] - 6.5 * (floor_850 - attitash.base_m) / 1000.0) < 1e-6
    top = features.hourly_features(profile(config.levels_for("newengland")), attitash.summit_m)
    assert read["t0"].iloc[0] > top["t0"].iloc[0] + 3


def test_the_sierra_asks_for_exactly_what_it_did():
    before = openmeteo.FORECAST_SURFACE_VARS + openmeteo.level_variables() + [openmeteo.WIND_DIRECTION]
    assert pipeline.forecast_variables("tahoe") == before
    assert pipeline.forecast_variables("mammoth") == before
    seattle = pipeline.forecast_variables("seattle")
    assert set(before) < set(seattle) and len(seattle) == len(before) + 12
    assert "temperature_925hPa" in seattle and "geopotential_height_950hPa" in seattle
    newengland = pipeline.forecast_variables("newengland")
    assert set(seattle) < set(newengland) and len(newengland) == len(before) + 20
    assert "relative_humidity_1000hPa" in newengland and "wind_speed_975hPa" in newengland


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
    assert abs(usage.resort_run_calls("newengland") - (usage.CALLS_PER_RESORT_RUN + 5 * usage.EXTRA_LEVEL_CALLS)) < 1e-9
    assert abs((cost("newengland") - cost("tahoe")) / 5 - usage.EXTRA_LEVEL_CALLS) < 0.01
    assert usage.planned() <= usage.PLAN_LIMIT


def test_seattle_blends_with_its_own_weights_and_the_rest_with_the_sierras():
    sierra = json.loads((MODELS / "weights.json").read_text())
    for region in ("tahoe", "mammoth", "newengland"):
        assert pipeline.load_weights(region) == sierra, region
    seattle = pipeline.load_weights("seattle")
    assert seattle == json.loads((MODELS / "weights_seattle.json").read_text())
    assert set(seattle) == set(config.DET_MODELS) and abs(sum(seattle.values()) - 1) < 0.005


def test_seattle_splits_rain_from_snow_with_its_own_curve_and_the_rest_with_the_sierras():
    sierra = phase.load()
    assert sierra == ("wet-bulb logistic", {"center_c": 1.25, "width_c": 0.2})
    for region in ("tahoe", "mammoth", "newengland"):
        assert phase.load(region) == sierra, region
        assert pipeline.load_snow_model(region)[0].phase_params == sierra[1], region
    kind, params = phase.load("seattle")
    assert kind == sierra[0] and params["center_c"] < sierra[1]["center_c"]
    model = pipeline.load_snow_model("seattle")[0]
    assert (model.phase_kind, model.phase_params) == (kind, params)
    # At one degree of wet-bulb the Sierra's curve still calls most of it snow; Seattle's calls most of it rain.
    hour = pd.DataFrame({"tw0": [1.0]})
    assert phase.hourly_fraction(hour, 1000.0, *sierra)[0] > 0.7
    assert phase.hourly_fraction(hour, 1000.0, kind, params)[0] < 0.3


def test_the_sierra_block_is_read_as_it_was_and_the_cascades_have_their_own():
    lats, lons, iy, ix = omfiles_s3.grid_025()
    assert (lats[0], lats[-1], lons[0], lons[-1]) == (36.25, 40.25, -121.5, -118.0)
    assert (iy, ix) == (slice(505, 522), slice(234, 249))
    lats, lons, _, _ = omfiles_s3.grid_025(omfiles_s3.CASCADES_BLOCK)
    for station in config.SEATTLE_STATIONS.values():
        assert lats[0] <= station.lat <= lats[-1] and lons[0] <= station.lon <= lons[-1], station.name


def test_a_sensor_gets_the_profile_of_the_node_nearest_it():
    station = config.SEATTLE_STATIONS["791:WA:SNTL"]                     # Stevens Pass, 47.746 N 121.093 W
    frames = {(47.75, -121.0): profile(config.levels_for("seattle"), hours=72, t700=-8.0),
              (47.75, -121.25): profile(config.levels_for("seattle"), hours=72, t700=5.0)}
    days = pd.date_range("2026-12-01", periods=3)
    gains = pd.DataFrame({"station": station.triplet, "date": days, "swe_gain_mm": [10.0, 2.0, 0.0],
                          "prec_gain_mm": [20.0, 2.0, 12.0], "depth_gain_cm": [5.0, 0.0, 0.0]})
    hourly, observed, elev_m = train.sensor_hourly({station.triplet: station}, gains, frames)[station.triplet]
    assert elev_m == station.elev_m and hourly["t0"].iloc[0] < 5
    assert list(observed.index) == [days[0], days[2]] and list(observed["fraction"]) == [0.5, 0.0]
    assert observed["end_utc"].iloc[0] == pd.Timestamp("2026-12-02 08:00")


def test_a_sensor_outside_tahoe_makes_snow_days_at_its_own_height():
    station = config.SEATTLE_STATIONS["791:WA:SNTL"]
    hourly = features.hourly_features(profile(config.levels_for("seattle"), hours=96), station.elev_m)
    windows = features.window_features(hourly)
    days = pd.date_range("2026-12-01", periods=3)
    gains = pd.DataFrame({"swe_gain_mm": [10.0, 0.0, 5.0], "depth_gain_cm": [12.0, 0.0, 4.0],
                          "prec_gain_mm": [11.0, 0.0, 5.0]}, index=days)
    events = dataset.snotel_events(gains, station.triplet, windows, station.elev_m)
    assert list(events["elev_m"]) == [station.elev_m] * 3 and list(events["slr"].round(1))[::2] == [12.0, 8.0]
    assert events["source"].eq("snotel").all() and events["t0"].notna().all()


def test_the_density_check_on_record_keeps_the_sierra_model():
    record = json.loads((MODELS / "snow_ratio_check_seattle.json").read_text())
    assert record["in_use"].endswith("trained in the Sierra") and record["checked_on"]["days"] >= 200
    ours = record["sierra_model"]["snow_error_in"]
    assert ours < record["kuchera"]["snow_error_in"] and ours < record["flat_10_to_1"]["snow_error_in"]
    assert record["pooled_refit_each_station_held_out"]["snow_error_in"] > ours - 0.05
    assert not (MODELS / "snow_ratio_seattle.joblib").exists()
