"""The fourth collector's regions: the USA's western regions added after the third collector's plan filled."""
import json
import math
import os
import subprocess
import sys

from tahoe_snow import calibrate, config, pipeline, usage
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS, ALL_STATIONS, FIT_BOXES, MODELS, MORE_BBOX, MORE_STATIONS
from tahoe_snow.snow import observations, phase, train

NORTH = {'westidaho': 6, 'wyoming': 7, 'southutah': 3, 'arizona': 3, 'lasvegas': 1, 'socal': 5, 'juneau': 3, 'valdez':
         5, 'inlandnw': 6, 'nwmontana': 8,
         # Four regions made for classic descents far from any other region.
         'rubymountains': 1, 'lasal': 1, 'denali': 1, 'wrangellstelias': 2}
SHARED = {"delano": "eaglepoint", "humphreys": "azsnowbowl", "snowsummit": "bearmountain", "mttroy": "eaglecrest",
          "benstewart": "eaglecrest", "girlsmountain": "thompsonpass", "stevenspeak": "lookoutpass"}


def mountains(region: str) -> list:
    return [r for r in ALL_RESORTS.values() if r.region == region]


def km(a, b) -> float:
    east = math.radians(b.lon - a.lon) * math.cos(math.radians((a.lat + b.lat) / 2))
    return 6371 * math.hypot(east, math.radians(b.lat - a.lat))


def test_the_ten_regions_are_the_fourth_collectors_and_in_the_usa():
    # Alaska is the fourth collector's too, moved from the third on 2026-11-26 (see test_west.py).
    assert {key for key, region in ALL_REGIONS.items() if region.collector == "north"} == set(NORTH) | {"alaska"}
    for key, count in NORTH.items():
        region = ALL_REGIONS[key]
        assert (region.country, region.at, region.every_h) == ("USA", (5, 13, 21), 8), key
        assert len(mountains(key)) == count, key
    assert not set(NORTH) & set(config.REGIONS)


def test_every_mountain_sits_in_its_regions_box_and_names_one_of_its_sensors():
    for key in NORTH:
        lat0, lat1, lon0, lon1 = MORE_BBOX[key]
        for r in mountains(key):
            assert r.base_m < r.summit_m, r.key
            assert lat0 < r.lat < lat1 and lon0 < r.lon < lon1, r.key
            assert r.station is None or r.station in MORE_STATIONS[key], r.key
            assert (r.kind == "backcountry") == (r.pass_group == "Backcountry"), r.key
        for station in MORE_STATIONS.get(key, {}).values():
            assert lat0 < station.lat < lat1 and lon0 < station.lon < lon1, station.name
            assert station.triplet in ALL_STATIONS


def test_sensor_clocks_and_low_levels():
    # Alaska's sensors keep Alaska standard time; every other state's the Pacific standard clock.
    assert {key for key in NORTH if ALL_REGIONS[key].std_offset_h == 9} == {"juneau", "valdez", "denali", "wrangellstelias"}
    # A base under about 1,450 m needs levels below 850 hPa.
    for key in NORTH:
        lowest = min(r.base_m for r in mountains(key))
        assert (lowest < 1450) == bool(ALL_REGIONS[key].low_levels), key
    assert ALL_REGIONS["juneau"].low_levels == (975, 950, 925, 900)


def test_close_neighbours_share_weather_within_their_region():
    north = {r.key: r for key in NORTH for r in mountains(key)}
    assert {key: r.weather_from for key, r in north.items() if r.weather_from} == SHARED
    for key, neighbour in SHARED.items():
        mine, theirs = north[key], north[neighbour]
        assert theirs.weather_from is None and theirs.region == mine.region
        assert km(mine, theirs) < 8, key


def test_the_regions_with_sensors_are_wired_for_fitting():
    assert set(FIT_BOXES) <= set(MORE_BBOX) and set(FIT_BOXES) <= set(MORE_STATIONS)
    for key in FIT_BOXES:
        assert calibrate.REGIONS[key] == (MORE_STATIONS[key], MORE_BBOX[key], f"{key}_daily")
        assert observations.BOXES[f"{key}box"][1] == MORE_BBOX[key]
        box, block = train.REGION_BOXES[key]
        assert box == f"{key}box" and block[0] <= MORE_BBOX[key][0] and block[1] >= MORE_BBOX[key][1]
    # Southern California and Juneau have no sensors, and Valdez's one corrects nothing.
    assert not {"socal", "juneau", "valdez"} & set(FIT_BOXES)
    assert [r.key for r in mountains("valdez") if r.station and r.corrected] == []


def test_the_fourth_collector_sees_its_regions_and_plans_only_them():
    code = ("from tahoe_snow import config, usage; "
            "print(config.COLLECTOR, sorted(config.REGIONS), len(config.RESORTS), "
            "sum(usage.pulls(r) for r in config.REGIONS), round(usage.planned()))")
    out = subprocess.run([sys.executable, "-c", code], env={**os.environ, "SNOW_COLLECTOR": "north"}, text=True,
                         capture_output=True, check=True).stdout.strip()
    assert out.startswith(f"north {sorted([*NORTH, 'alaska'])} 59 51 ")
    assert 8100 < int(out.rsplit(" ", 1)[1]) < 8700


def test_each_fitted_region_has_its_correction_weights_and_split_and_two_have_their_own_ratio():
    for key in FIT_BOXES:
        assert (MODELS / f"bias_{key}.json").exists(), key
        weights = json.loads((MODELS / f"weights_{key}.json").read_text())
        assert set(weights) == set(config.DET_MODELS) and abs(sum(weights.values()) - 1) < 0.005, key
        kind, params = phase.load(key)
        assert kind == "wet-bulb logistic" and 0 <= params["center_c"] <= 2, key
        assert (MODELS / f"snow_ratio_check_{key}.json").exists(), key
    # A region's own ratio is kept only where it clearly beat the Sierra's at stations left out of the fit. Las
    # Vegas's check has twelve days at one station, too few to say anything.
    own = {key for key in FIT_BOXES if (MODELS / f"snow_ratio_{key}.joblib").exists()}
    assert own == {"southutah", "arizona"}
    for key in own:
        check = json.loads((MODELS / f"snow_ratio_check_{key}.json").read_text())
        assert check["pooled_refit_each_station_held_out"]["snow_error_in"] < check["sierra_model"]["snow_error_in"] - 0.03
    assert json.loads((MODELS / "snow_ratio_check_lasvegas.json").read_text())["checked_on"]["days"] < 30


def test_a_summit_over_the_highest_usual_level_reads_one_above_it():
    # Denali's summit (6,190 m) and St. Elias's (5,489 m) are at or above 500 hPa, the highest level read elsewhere.
    assert {key for key, region in ALL_REGIONS.items() if region.high_levels} == {"denali", "wrangellstelias"}
    assert config.levels_for("denali") == config.PRESSURE_LEVELS + [400]
    assert usage.resort_run_calls("denali") == usage.CALLS_PER_RESORT_RUN + usage.EXTRA_LEVEL_CALLS
    assert "temperature_400hPa" in pipeline.forecast_variables("denali")
    # Baffin Island's line starts on sea ice, so it reads down to 1000 hPa; both of Canada's are the second collector's.
    assert ALL_REGIONS["baffin"].low_levels == (1000, 975, 950, 925, 900)
    assert {ALL_REGIONS[key].collector for key in ("baffin", "waddington")} == {"canada"}
