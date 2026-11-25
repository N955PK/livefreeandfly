"""Canada's snow stations: British Columbia's network files and Alberta's snow pillows."""
import pandas as pd
import pytest

from tahoe_snow import config, pipeline, season
from tahoe_snow.sources import abrivers, bcasws

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


def test_seven_canadian_mountains_are_shown_a_station_and_none_is_corrected_against_it():
    paired = {key: resort.station for key, resort in config.ALL_RESORTS.items()
              if config.ALL_REGIONS[resort.region].country == "Canada" and resort.station}
    assert paired == {"silverstar": "2F10P:BCASWS", "cypress": "3A30P:BCASWS", "grouse": "3A09P:BCASWS",
                      "rogerspass": "2A34P:BCASWS", "fernie": "2C09Q:BCASWS", "bowsummit": "2A32P:BCASWS",
                      "sunshine": "05BB803:ABRIVERS"}
    for key, triplet in paired.items():
        station = config.ALL_STATIONS[triplet]
        assert not station.corrects and pipeline.correcting_station(config.ALL_RESORTS[key]) is None, key
        assert station.source in pipeline.HOURLY_READERS and station.source in season.NO_RECORD, key
    assert config.ALL_RESORTS["rogerspass"].weak_match
    assert not config.ALL_STATIONS["2A32P:BCASWS"].depth and not config.ALL_STATIONS["05BB803:ABRIVERS"].depth


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
