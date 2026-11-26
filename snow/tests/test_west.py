"""The third collector's regions: Montana, Sun Valley, Oregon, New Mexico, Alaska and Southwest Colorado."""
import json
import math
import os
import subprocess
import sys

from tahoe_snow import biascorrect, calibrate, config
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS, ALL_STATIONS, MODELS
from tahoe_snow.snow import observations, phase, ratio, train
from tahoe_snow.sources import omfiles_s3

WEST = {"montana": 6, "sunvalley": 6, "oregon": 11, "newmexico": 9, "alaska": 7, "swcolorado": 15}
# Where each region's mountains lie: south, north, west, east.
BOXES = {"montana": (44.9, 46.9, -111.5, -109.9), "sunvalley": (43.4, 44.4, -115.3, -114.3),
         "oregon": (43.5, 45.5, -122.1, -121.5), "newmexico": (35.7, 36.8, -106.5, -105.2),
         "alaska": (60.6, 61.8, -149.6, -149.0), "swcolorado": (37.4, 39.4, -108.2, -106.3)}
SHARED = {"abasin": "keystone", "lovelandpass": "loveland", "vailpass": "copper", "berthoud": "winterpark",
          "beehive": "bigsky", "dollar": "sunvalley", "tumalo": "bachelor", "wheelerpeak": "taos", "goldhill": "taos",
          "sunburst": "tincan", "highlands": "aspen", "buttermilk": "aspen"}
STATIONS = {"montana": config.MONTANA_STATIONS, "sunvalley": config.SUNVALLEY_STATIONS,
            "oregon": config.OREGON_STATIONS, "newmexico": config.NEWMEXICO_STATIONS,
            "alaska": config.ALASKA_STATIONS, "swcolorado": config.SWCOLORADO_STATIONS}
BBOXES = {"montana": config.MONTANA_BBOX, "sunvalley": config.SUNVALLEY_BBOX, "oregon": config.OREGON_BBOX,
          "newmexico": config.NEWMEXICO_BBOX, "alaska": config.ALASKA_BBOX, "swcolorado": config.SWCOLORADO_BBOX}


def mountains(region: str) -> list:
    return [r for r in ALL_RESORTS.values() if r.region == region]


def km(a, b) -> float:
    east = math.radians(b.lon - a.lon) * math.cos(math.radians((a.lat + b.lat) / 2))
    return 6371 * math.hypot(east, math.radians(b.lat - a.lat))


def test_the_six_regions_are_the_third_collectors_and_in_the_usa():
    # Colorado is the third collector's too, moved from the first on 2026-11-26 (see test_colorado.py).
    assert {key for key, region in ALL_REGIONS.items() if region.collector == "west"} == set(WEST) | {"colorado"}
    for key in WEST:
        region = ALL_REGIONS[key]
        assert (region.country, region.at, region.every_h) == ("USA", (5, 13, 21), 8), key
    # None of them is the first collector's, whose plan was full.
    assert not set(WEST) & set(config.REGIONS)


def test_every_mountain_is_where_its_region_is_and_its_sensor_is_the_regions():
    for key, count in WEST.items():
        found = mountains(key)
        south, north, west, east = BOXES[key]
        assert len(found) == count, key
        for r in found:
            assert r.base_m < r.summit_m, r.key
            assert south < r.lat < north and west < r.lon < east, r.key
            assert r.station is None or r.station in STATIONS[key], r.key
            assert (r.kind == "backcountry") == (r.pass_group == "Backcountry"), r.key


def test_the_sensors_are_on_the_pacific_clock_except_alaskas():
    assert {key: ALL_REGIONS[key].std_offset_h for key in WEST} == {
        "montana": 8, "sunvalley": 8, "oregon": 8, "newmexico": 8, "alaska": 9, "swcolorado": 8}
    assert ALL_REGIONS["alaska"].tz == "America/Anchorage" and ALL_REGIONS["sunvalley"].tz == "America/Boise"


def test_low_ground_reads_lower_pressure_levels():
    # A base under about 1,450 m needs levels below 850 hPa: Oregon's (Skibowl, 1,097 m) and Alaska's (Alyeska, 76 m).
    for key in WEST:
        lowest = min(r.base_m for r in mountains(key))
        assert (lowest < 1450) == bool(ALL_REGIONS[key].low_levels), key
    assert ALL_REGIONS["oregon"].low_levels == (900,)
    assert ALL_REGIONS["alaska"].low_levels == (1000, 975, 950, 925, 900)


def test_close_neighbours_share_weather_within_their_region():
    west = {r.key: r for key in [*WEST, "colorado"] for r in mountains(key)}
    assert {key: r.weather_from for key, r in west.items() if r.weather_from} == SHARED
    for key, neighbour in SHARED.items():
        mine, theirs = west[key], west[neighbour]
        assert theirs.weather_from is None and theirs.region == mine.region
        # The six new regions share only under 8 km; Colorado's pairs were set earlier, some a little further.
        assert km(mine, theirs) < (20 if mine.region == "colorado" else 8), key


def test_each_fitting_box_holds_the_regions_sensors_and_mountains():
    for key in WEST:
        lat0, lat1, lon0, lon1 = BBOXES[key]
        for place in [*STATIONS[key].values(), *mountains(key)]:
            assert lat0 < place.lat < lat1 and lon0 < place.lon < lon1, getattr(place, "name", key)
        assert set(STATIONS[key]) <= set(ALL_STATIONS)


def test_the_avalanche_centers_are_each_regions_own():
    assert {key: ALL_REGIONS[key].avalanche for key in WEST} == {
        "montana": ("GNFAC",), "sunvalley": ("SNFAC",), "oregon": ("NWAC", "COAA"), "newmexico": ("TAC",),
        "alaska": ("CNFAIC", "HPAC"), "swcolorado": ("CAIC",)}


def test_the_third_collector_sees_its_six_regions_and_plans_only_them():
    code = ("from tahoe_snow import config, usage; "
            "print(config.COLLECTOR, sorted(config.REGIONS), len(config.RESORTS), "
            "sum(usage.pulls(r) for r in config.REGIONS), round(usage.planned()))")
    out = subprocess.run([sys.executable, "-c", code], env={**os.environ, "SNOW_COLLECTOR": "west"}, text=True,
                         capture_output=True, check=True).stdout.strip()
    assert out.startswith(f"west {sorted([*WEST, 'colorado'])} 68 56 ")
    # 56 pulls three times a day, with Oregon's one and Alaska's five lower levels: inside the day's 10,000.
    assert 8700 < int(out.rsplit(" ", 1)[1]) < 9300


def test_each_region_has_its_own_correction_weights_and_split():
    for key in WEST:
        assert calibrate.REGIONS[key] == (STATIONS[key], BBOXES[key], f"{key}_daily")
        assert observations.BOXES[f"{key}box"][1] == BBOXES[key]
        block = getattr(omfiles_s3, f"{key.upper()}_BLOCK")
        assert train.REGION_BOXES[key] == (f"{key}box", block)
        # The block of upper air holds the whole box.
        assert block[0] <= BBOXES[key][0] and block[1] >= BBOXES[key][1]
        assert block[2] <= BBOXES[key][2] and block[3] >= BBOXES[key][3]
        correction = biascorrect.from_json(json.loads((MODELS / f"bias_{key}.json").read_text()))
        for r in mountains(key):
            if r.station and r.corrected:
                # Soldier Mountain's sensor takes the curve pooled over its region, which did better there.
                assert correction.fitted(r.station) == (r.station not in calibrate.POOLED_ONLY.get(key, ())), r.key
        weights = json.loads((MODELS / f"weights_{key}.json").read_text())
        assert set(weights) == set(config.DET_MODELS) and abs(sum(weights.values()) - 1) < 0.005
        kind, params = phase.load(key)
        assert kind == "wet-bulb logistic" and 0 <= params["center_c"] <= 2, key
    # Alaska's sensors stamp their days on Alaska's clock, an hour behind the Pacific one the rest keep.
    assert calibrate.SENSOR_OFFSET_H == train.SENSOR_OFFSET_H == {"alaska": 9}
    assert calibrate.POOLED_ONLY["sunvalley"] == (ALL_RESORTS["soldier"].station,)


def test_only_the_summit_climb_with_a_low_sensor_is_left_uncorrected():
    assert [r.key for key in WEST for r in mountains(key) if r.station and not r.corrected] == ["hoodsouth"]


def test_three_regions_have_their_own_snow_ratio_and_three_keep_the_sierras():
    for key in WEST:
        check = json.loads((MODELS / f"snow_ratio_check_{key}.json").read_text())
        pooled = check["pooled_refit_each_station_held_out"]["snow_error_in"]
        sierra = check["sierra_model"]["snow_error_in"]
        own = (MODELS / f"snow_ratio_{key}.joblib").exists()
        # A region's own ratio is kept only where it beat the Sierra's at stations left out of the fit.
        assert own == (key in ("montana", "alaska", "swcolorado")), key
        assert (pooled < sierra - 0.03) == own, key
        assert ratio.model_files(key)[0] == MODELS / (f"snow_ratio_{key}.joblib" if own else "snow_ratio.joblib")
