"""Shasta: the Ski Park and Mt. Ashland, and Mt. Shasta, Castle Lake and Lassen Peak, built twice a day."""
import pandas as pd

from tahoe_snow import calibrate, config, pipeline, usage
from tahoe_snow.config import MODELS, RESORTS
from tahoe_snow.snow import phase, ratio


def test_the_shasta_mountains_are_where_they_should_be():
    found = config.resorts_in("shasta")
    assert [r.key for r in found] == ["shastaskipark", "ashland", "shasta", "castlelake", "lassen"]
    for r in found:
        assert r.base_m < r.summit_m, r.key
        # Lassen Peak in the south to Mt. Ashland, over the Oregon line, in the north.
        assert 40.4 < r.lat < 42.2 and -122.8 < r.lon < -121.4, r.key
        assert r.station is None or r.station in config.SHASTA_STATIONS, r.key
        # Every base is above the 850 hPa level, so the region reads no lower ones.
        assert r.base_m > 1450, r.key
    assert {r.key for r in found if r.kind == "backcountry"} == {"shasta", "castlelake", "lassen"}
    assert config.levels_for("shasta") == config.PRESSURE_LEVELS
    assert all(s.source == "cdec" for s in config.SHASTA_STATIONS.values())


def test_mt_shasta_is_shown_its_sensor_and_not_corrected_by_it():
    # Sand Flat is 1,158 m under the mountain's middle: right for the Ski Park beside it, not for the summit.
    assert pipeline.correcting_station(RESORTS["shasta"]) is None and RESORTS["shasta"].station == "SDF:CDEC"
    assert pipeline.correcting_station(RESORTS["shastaskipark"]) == "SDF:CDEC"
    assert pipeline.correcting_station(RESORTS["lassen"]) == "LLP:CDEC"


def test_all_five_ask_for_weather_twice_a_day():
    region = config.REGIONS["shasta"]
    assert usage.pulls("shasta") == 5 and (region.at, region.every_h) == ((5, 17), 12)
    assert round(usage.planned({"shasta": region})) == round(5 * 2 * usage.CALLS_PER_RESORT_RUN)
    assert region.avalanche == ("MSAC",) and pipeline.snotel_offset_h(RESORTS["lassen"]) == 8


def test_shasta_has_no_models_of_its_own_and_uses_the_sierras():
    # Its water test can be run again, but nothing came of it: the pillows there miss the rain.
    assert calibrate.REGIONS["shasta"] == (config.SHASTA_STATIONS, config.SHASTA_BBOX, "shasta_daily")
    assert not list(MODELS.glob("*shasta*"))
    assert "shasta" not in pipeline.load_corrections()
    assert pipeline.load_weights("shasta") == pipeline.load_weights("tahoe")
    assert phase.load("shasta") == phase.load() and ratio.model_files("shasta")[0] == MODELS / "snow_ratio.joblib"


def test_a_region_of_pillows_alone_is_read_without_gauges(tmp_path, monkeypatch):
    monkeypatch.setattr(calibrate, "TABLES", tmp_path)
    days = pd.DataFrame({"station": "SDF:CDEC", "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                         "swe_gain_mm": [12.0, -3.0, None]})
    days.to_parquet(tmp_path / "pillows.parquet")
    observed = calibrate.observed_daily("pillows")["observed_mm"]
    assert observed.iloc[:2].tolist() == [12.0, 0.0] and pd.isna(observed.iloc[2])
