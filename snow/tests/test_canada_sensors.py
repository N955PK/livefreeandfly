"""Canada's snow stations: British Columbia's network files and Alberta's snow pillows."""
import pandas as pd
import pytest

from tahoe_snow import calibrate, config, pipeline, season
from tahoe_snow.sources import abrivers, bcasws, snotel

WATER = """DATE(UTC),1A01P Yellowhead Lake,2F10P Silver Star Mountain,2A32P Wildcat Creek
2026-11-24 21:00,91,104,77
2026-11-24 22:00,91,,77
2026-11-24 23:00,,105,9999
"""
DEPTH = """DATE(UTC),1A01P Yellowhead Lake,2F10P Silver Star Mountain
2026-11-24 21:00,30,33
2026-11-24 22:00,30,NaN
2026-11-24 23:00,31,34
"""
AIR = """DATE(UTC),2F10P Silver Star Mountain
2026-11-24 23:00,-4.2
"""


def test_a_british_columbia_station_is_its_column_of_each_measures_file_in_utc():
    frame = bcasws.parse({"SW": WATER, "SD": DEPTH, "TA": AIR}, "2F10P")
    assert list(frame.columns) == ["swe_mm", "depth_cm", "tobs_c"]
    assert list(frame.index) == [pd.Timestamp("2026-11-24 21:00"), pd.Timestamp("2026-11-24 23:00")]
    assert frame.loc["2026-11-24 23:00"].tolist() == [105.0, 34.0, -4.2]
    assert pd.isna(frame.loc["2026-11-24 21:00", "tobs_c"])


def test_a_station_with_no_depth_gauge_has_water_alone_and_a_wild_reading_is_dropped():
    frame = bcasws.parse({"SW": WATER, "SD": DEPTH, "TA": AIR}, "2A32P")
    assert frame["swe_mm"].tolist() == [77.0, 77.0] and frame["depth_cm"].isna().all()
    assert bcasws.parse({"SW": WATER, "SD": DEPTH, "TA": AIR}, "9Z99P").empty


def test_an_alberta_pillow_is_five_days_of_water_in_millimeters():
    payload = [{"station_name": "Sunshine Village - EPA", "ts_unitsymbols": ["mm"],
                "data": [["2026-11-24 16:30:00", 55.0], ["2026-11-24 16:45:00", None], ["2026-11-24 17:00:00", 56.0]]}]
    frame = abrivers.parse(payload)
    assert frame["swe_mm"].tolist() == [55.0, 56.0] and frame.index[-1] == pd.Timestamp("2026-11-24 17:00")
    with pytest.raises(ValueError):
        abrivers.parse([{"ts_unitsymbols": ["in"], "data": []}])


def test_eight_canadian_mountains_are_shown_a_station_and_six_are_corrected_against_it():
    paired = {key: resort.station for key, resort in config.ALL_RESORTS.items()
              if config.ALL_REGIONS[resort.region].country == "Canada" and resort.station}
    assert paired == {"silverstar": "2F10P:BCASWS", "cypress": "3A30P:BCASWS", "grouse": "3A09P:BCASWS",
                      "revelstoke": "2A06P:BCASWS", "rogerspass": "2A34P:BCASWS", "fernie": "2C09Q:BCASWS",
                      "bowsummit": "2A32P:BCASWS", "sunshine": "05BB803:ABRIVERS"}
    # Mount Strachan has no water sensor and Alberta keeps no record, so those two are only shown.
    shown_only = {"cypress", "sunshine"}
    for key, triplet in paired.items():
        station = config.ALL_STATIONS[triplet]
        corrects = pipeline.correcting_station(config.ALL_RESORTS[key]) is not None
        assert station.corrects == corrects == (key not in shown_only), key
        assert station.source in pipeline.HOURLY_READERS and station.source in season.NO_RECORD, key
    assert config.ALL_RESORTS["rogerspass"].weak_match
    for triplet in ("2A32P:BCASWS", "2A06P:BCASWS", "05BB803:ABRIVERS"):
        assert not config.ALL_STATIONS[triplet].depth


def test_each_western_canadian_region_has_a_water_correction_holding_its_paired_stations_own_curves(monkeypatch):
    monkeypatch.setattr(pipeline, "RESORTS", config.ALL_RESORTS)
    corrections = pipeline.load_corrections()
    for region in ("okanagan", "bccoast", "powderhighway", "eastkootenays", "rockies"):
        stations, _, _ = calibrate.REGIONS[region]
        assert all(s.source == "bcasws" and s.corrects for s in stations.values()), region
        assert all(corrections[region].fitted(key) for key in stations), region
        assert (config.MODELS / f"weights_{region}.json").exists(), region
    assert "quebec" not in corrections
    for key in ("silverstar", "grouse", "revelstoke", "rogerspass", "fernie", "bowsummit"):
        resort = config.ALL_RESORTS[key]
        assert pipeline.water_correction(resort, corrections[resort.region]) == "station", key
    for key in ("bigwhite", "whistler", "cypress", "kickinghorse", "lakelouise", "sunshine", "tremblant"):
        resort = config.ALL_RESORTS[key]
        assert pipeline.water_correction(resort, corrections.get(resort.region)) is None, key


def test_the_long_record_is_read_as_daily_values_at_midnight_pacific_standard_time():
    hours = pd.date_range("2025-01-01 00:00", "2025-01-04 12:00", freq="h")
    water = pd.Series(100.0, index=hours)
    water[hours >= "2025-01-02 08:00"] = 112.0       # the reading that ends January 1, Pacific standard time
    water[hours >= "2025-01-03 07:00"] = 120.0
    water[pd.Timestamp("2025-01-03 08:00")] = 900.0  # one stray hour at midnight
    frame = bcasws.daily_values(pd.DataFrame({"swe_mm": water, "prec_mm": water + 50, "tobs_c": -5.0}))
    assert frame.loc["2025-01-01", "swe_mm"] == 112.0 and frame.loc["2025-01-02", "swe_mm"] == 120.0
    assert frame.loc["2025-01-01", "prec_mm"] == 162.0
    assert frame.loc["2025-01-01", ["tavg_c", "tmax_c", "tmin_c"]].tolist() == [-5.0, -5.0, -5.0]
    gains = snotel.daily_gains(frame)
    assert gains.loc["2025-01-02", "swe_gain_mm"] == 8.0
    # December 31 has eight hours of temperature here, too few for a day's.
    assert pd.isna(frame.loc["2024-12-31", "tavg_c"])


def test_a_british_columbia_station_is_read_in_utc_and_an_alberta_one_on_mountain_standard_time(monkeypatch):
    monkeypatch.setattr(pipeline, "RESORTS", config.ALL_RESORTS)
    monkeypatch.setattr(pipeline, "REGIONS", config.ALL_REGIONS)
    now = pd.Timestamp("2026-11-25 00:30")
    hours = pd.date_range("2026-11-22 00:00", periods=96, freq="h")
    stamps = pd.date_range("2026-11-20 00:00", "2026-11-24 23:00", freq="h")
    reading = pd.DataFrame({"swe_mm": 100.0, "depth_cm": 30.0, "tobs_c": -4.0}, index=stamps)
    monkeypatch.setattr(bcasws, "hourly", lambda *a, **k: reading)
    monkeypatch.setattr(abrivers, "hourly", lambda *a, **k: reading[["swe_mm"]].iloc[:-7])
    told = pipeline.observed(config.ALL_RESORTS["silverstar"], now, hours)
    assert told["station"] == "Silver Star Mountain" and told["as_of_utc"] == "2026-11-24T23:00:00Z"
    assert (told["depth_in"], told["water_in"], told["temp_f"]) == (12, 3.9, 25)
    # Sunshine's last reading, 4 pm Mountain Standard Time, is 11 pm UTC; it has water and no depth.
    told = pipeline.observed(config.ALL_RESORTS["sunshine"], now, hours)
    assert told["as_of_utc"] == "2026-11-24T23:00:00Z" and told["depth_in"] is None and told["water_in"] == 3.9
