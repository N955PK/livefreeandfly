import numpy as np
import pandas as pd

from tahoe_snow.config import PRESSURE_LEVELS
from tahoe_snow.snow import dataset, features, ratio
from tahoe_snow.sources import ghcn, snotel


def make_profile(hours=72, t700=-8.0, precip=1.0, rh=95.0):
    """A standard-atmosphere-like profile: 6.5 C/km lapse, anchored at 700 hPa = 3000 m."""
    index = pd.date_range("2023-01-10", periods=hours, freq="h")
    heights = {850: 1450.0, 800: 1950.0, 750: 2450.0, 700: 3000.0, 650: 3600.0, 600: 4200.0, 550: 4850.0, 500: 5550.0}
    data = {"precipitation": np.full(hours, precip)}
    for level in PRESSURE_LEVELS:
        z = heights[level]
        data[f"temperature_{level}hPa"] = np.full(hours, t700 - 6.5 * (z - 3000.0) / 1000.0)
        data[f"relative_humidity_{level}hPa"] = np.full(hours, rh)
        data[f"wind_speed_{level}hPa"] = np.full(hours, 36.0)
        data[f"geopotential_height_{level}hPa"] = np.full(hours, z)
    return pd.DataFrame(data, index=index)


def test_hourly_features_interpolate_to_station_height():
    hourly = features.hourly_features(make_profile(), elev_m=2450.0)
    assert abs(hourly["t0"].iloc[0] - (-8.0 + 6.5 * 0.55)) < 1e-6
    assert abs(hourly["t1000"].iloc[0] - (hourly["t0"].iloc[0] - 6.5)) < 0.05
    assert abs(hourly["wind0"].iloc[0] - 10.0) < 1e-6
    assert abs(hourly["lapse"].iloc[0] - 6.5) < 0.05
    assert hourly["tw0"].iloc[0] <= hourly["t0"].iloc[0]


def test_window_features_weight_by_precipitation():
    profile = make_profile(hours=48)
    hourly = features.hourly_features(profile, elev_m=2450.0)
    hourly.loc[hourly.index[:24], "t0"] = -2.0
    hourly.loc[hourly.index[:24], "precip"] = [0.0] * 23 + [3.0]
    hourly.loc[hourly.index[:23], "t0"] = -20.0
    window = features.window_features(hourly).iloc[23]
    assert abs(window["t0"] - (-2.0)) < 1e-9
    assert abs(window["model_precip_mm"] - 3.0) < 1e-9
    assert not window["model_dry"]


def test_window_features_dry_model_uses_plain_mean():
    hourly = features.hourly_features(make_profile(hours=30, precip=0.0), elev_m=2450.0)
    window = features.window_features(hourly).iloc[-1]
    assert window["model_dry"]
    assert abs(window["t0"] - hourly["t0"].iloc[0]) < 1e-9


def test_manual_window_ends_at_local_observation_hour():
    dates = pd.DatetimeIndex(["2023-01-15", "2023-04-15"])
    end = dataset.manual_window_end_utc(dates, pd.Series([8.0, np.nan]))
    assert end[0] == pd.Timestamp("2023-01-15 16:00")
    assert end[1] == pd.Timestamp("2023-04-15 14:00")


def test_season_label():
    assert list(dataset.season_of(pd.DatetimeIndex(["2022-11-01", "2023-03-01", "2023-10-01"]))) == [2023, 2023, 2024]


def test_winter_spans_cover_only_winter_months():
    spans = dataset.winter_spans("2021-03-25", "2022-12-15")
    assert spans[0] == ("2021-03-25", "2021-03-31")
    assert ("2021-07-01", "2021-07-31") not in spans
    assert spans[-1] == ("2022-12-01", "2022-12-15")


def _events(n=600, seed=0):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({name: rng.normal(size=n) for name in features.FEATURES})
    frame["t0"] = rng.uniform(-15, 0, n)
    frame["tmax_col"] = frame["t0"] + 1.0
    frame["liquid_mm"] = rng.uniform(3, 40, n)
    frame["slr"] = 8.0 - 0.6 * frame["t0"] + rng.normal(0, 0.5, n)
    frame["snow_mm"] = frame["slr"] * frame["liquid_mm"]
    frame["season"] = rng.integers(2022, 2027, n)
    frame["station"] = rng.choice(["a", "b", "c"], n)
    frame["date"] = pd.Timestamp("2023-01-01")
    frame["tw0_max"] = -3.0
    frame["trace"] = False
    frame["hours_valid"] = 24.0
    return frame


def test_folds_never_share_a_season():
    events = _events()
    for season, train, test in ratio.folds(events, "season"):
        assert set(events.loc[train, "season"]).isdisjoint(set(events.loc[test, "season"]))
        assert (events.loc[test, "season"] == season).all()


def test_learned_models_recover_a_known_temperature_dependence():
    events = _events()
    table, _ = ratio.cross_validate(events)
    assert table.loc["ridge (all)", "slr_mae"] < 0.6
    assert table.loc["gradient boosting (temp + wind)", "slr_mae"] < 1.0
    assert table.loc["fixed 10:1", "slr_mae"] > 2.0
    assert table.loc["ridge (all)", "snow_mae_in"] < table.loc["Kuchera", "snow_mae_in"]


def test_ratio_filter_drops_rain_tiny_and_trace_events():
    events = _events(50)
    events.loc[0, "tw0_max"] = 2.0
    events.loc[1, "liquid_mm"] = 1.0
    events.loc[2, "trace"] = True
    events.loc[3, "slr"] = 80.0
    events.loc[4, "t0"] = np.nan
    assert len(dataset.ratio_filter(events)) == 45


def test_saved_model_reloads_identically(tmp_path, monkeypatch):
    monkeypatch.setattr(ratio, "MODELS", tmp_path)
    events = _events(200)
    fitted = ratio.fit_final(events, "ridge (all)", ratio.candidates()["ridge (all)"])
    assert np.allclose(ratio.load().predict(events), fitted.predict(events))


def test_ghcn_parse_units_flags_and_obs_hour():
    text = ('"STATION","DATE","PRCP","PRCP_ATTRIBUTES","SNOW","SNOW_ATTRIBUTES"\n'
            '"USC00048758","2019-02-15","41.9",",,7,0800","559.0",",,7,0800"\n'
            '"USC00048758","2019-02-16","","","T","T,,7,0800"\n'
            '"USC00048758","2019-02-17","5.0",",I,7,0800","10.0",",,7,"\n')
    frame = ghcn.parse(text)
    assert frame.loc["2019-02-15", "snow_mm"] == 559.0 and frame.loc["2019-02-15", "prcp_mm"] == 41.9
    assert frame.loc["2019-02-15", "snow_obs_hour"] == 8
    assert np.isnan(frame.loc["2019-02-16", "prcp_mm"]) and frame.loc["2019-02-16", "snow_trace"]
    assert np.isnan(frame.loc["2019-02-17", "prcp_mm"])
    assert np.isnan(frame.loc["2019-02-17", "snow_obs_hour"])


def test_snotel_parse_converts_units_and_drops_suspect():
    payload = [{"stationTriplet": "784:CA:SNTL", "data": [
        {"stationElement": {"elementCode": "WTEQ"},
         "values": [{"date": "2019-02-13", "value": 10.0, "qcFlag": "V"},
                    {"date": "2019-02-14", "value": 11.0, "qcFlag": "V"},
                    {"date": "2019-02-15", "value": 99.0, "qcFlag": "S"}]},
        {"stationElement": {"elementCode": "TAVG"}, "values": [{"date": "2019-02-13", "value": 32.0, "qcFlag": "V"}]}]}]
    frame = snotel.parse(payload)
    assert abs(frame.loc["2019-02-13", "swe_mm"] - 254.0) < 1e-9
    assert frame.loc["2019-02-13", "tavg_c"] == 0.0
    assert "2019-02-15" not in frame.index.astype(str)
    gains = snotel.daily_gains(frame)
    assert abs(gains.loc["2019-02-13", "swe_gain_mm"] - 25.4) < 1e-9


def test_phase_fraction_limits_and_monotonic():
    from tahoe_snow.snow import phase
    hourly = pd.DataFrame({"tw0": [-6.0, 0.0, 0.5, 1.0, 5.0], "t0": [-5.0, 0.5, 1.0, 1.5, 6.0],
                           "snow_level_m": [1000.0, 2300.0, 2500.0, 2700.0, 3500.0]})
    for kind in phase.GRIDS:
        fraction = phase.hourly_fraction(hourly, 2400.0, kind, phase.grid(kind)[len(phase.grid(kind)) // 2])
        assert fraction[0] > 0.99 and fraction[-1] < 0.01
        assert (np.diff(fraction) <= 1e-12).all()


def test_phase_observed_uses_larger_of_gauge_and_pillow():
    from tahoe_snow.snow import phase
    gains = pd.DataFrame({"prec_gain_mm": [20.0, 10.0, 2.0], "swe_gain_mm": [5.0, 15.0, 2.0]})
    out = phase.observed(gains)
    assert list(out["fraction"]) == [0.25, 1.0] and list(out["liquid_mm"]) == [20.0, 15.0]


def test_snow_model_zero_liquid_nan_profile_and_rain():
    from tahoe_snow.snow.model import SnowModel
    events = _events(200)
    fitted = ratio.candidates()["ridge (all)"].fit(events, events["slr"].to_numpy())
    model = SnowModel(fitted, "wet-bulb logistic", {"center_c": 0.5, "width_c": 0.4})
    cold = features.hourly_features(make_profile(hours=30, t700=-10.0), 2450.0)
    liquid = pd.Series(1.0, index=cold.index)
    liquid.iloc[5] = 0.0
    cold.iloc[7, cold.columns.get_loc("t1000")] = np.nan
    out = model.snowfall(cold, liquid, 2450.0)
    assert out["snow_cm"].iloc[5] == 0.0
    assert np.isnan(out["snow_cm"].iloc[7])
    assert out["snow_cm"].iloc[10] > 0.3
    warm = features.hourly_features(make_profile(hours=30, t700=6.0), 2450.0)
    assert model.snowfall(warm, pd.Series(1.0, index=warm.index), 2450.0)["snow_cm"].max() < 0.01


def test_levels_a_model_does_not_publish_are_ignored():
    full = make_profile(hours=30, t700=-8.0)
    sparse = full.copy()
    for level in (750, 650, 550):
        for field in features.LEVEL_FIELDS:
            sparse[f"{field}_{level}hPa"] = np.nan
    assert features.levels_in(sparse) == [850, 800, 700, 600, 500]
    a = features.hourly_features(full, 2450.0)
    b = features.hourly_features(sparse, 2450.0)
    assert not b[["t0", "t1000", "t2000", "tw0", "wind0", "rh0", "snow_level_m"]].isna().any().any()
    assert np.allclose(a["t0"], b["t0"], atol=0.05) and np.allclose(a["snow_level_m"], b["snow_level_m"], atol=30)
