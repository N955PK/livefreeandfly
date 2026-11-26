"""The fifth collector's regions (the East and the Midwest outside New England) and Canada's later regions."""
import math
import os
import subprocess
import sys

from tahoe_snow import config
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS, MORE_BBOX

EAST = {'newyork': 9, 'midatlantic': 10, 'lakesuperior': 7, 'michigan': 6, 'blackhills': 1}
CANADA = {'northbc': 4, 'ontario': 4, 'gaspesie': 7, 'newfoundland': 2, 'yukon': 2}
SHARED = {"canaanvalley": "timberlinewv", "nubsnob": "boynehighlands", "champsdemars": "hogsback"}


def mountains(region: str) -> list:
    return [r for r in ALL_RESORTS.values() if r.region == region]


def km(a, b) -> float:
    east = math.radians(b.lon - a.lon) * math.cos(math.radians((a.lat + b.lat) / 2))
    return 6371 * math.hypot(east, math.radians(b.lat - a.lat))


def test_the_five_eastern_regions_are_the_fifth_collectors():
    assert {key for key, region in ALL_REGIONS.items() if region.collector == "east"} == set(EAST)
    for key, count in EAST.items():
        region = ALL_REGIONS[key]
        # Built twice a day at New England's hours, on the region's own clock.
        assert (region.country, region.at, region.every_h) == ("USA", (4, 16), 12), key
        assert len(mountains(key)) == count, key
        # There are no snow sensors in the East or the Midwest within reach of a mountain.
        assert all(r.station is None for r in mountains(key)), key
    assert not set(EAST) & set(config.REGIONS)


def test_canadas_later_regions_are_the_second_collectors():
    for key, count in CANADA.items():
        region = ALL_REGIONS[key]
        assert (region.collector, region.country) == ("canada", "Canada"), key
        assert len(mountains(key)) == count, key
    # The western two are built at the West's hours, the eastern three at New England's.
    assert {key: ALL_REGIONS[key].at for key in CANADA} == {
        "northbc": (5, 13, 21), "yukon": (5, 13, 21), "ontario": (4, 16), "gaspesie": (4, 16), "newfoundland": (4, 16)}


def test_every_mountain_sits_in_its_regions_box_and_low_ground_reads_lower_levels():
    for key in [*EAST, *CANADA]:
        lat0, lat1, lon0, lon1 = MORE_BBOX[key]
        for r in mountains(key):
            assert r.base_m < r.summit_m, r.key
            assert lat0 < r.lat < lat1 and lon0 < r.lon < lon1, r.key
            assert (r.kind == "backcountry") == (r.pass_group == "Backcountry"), r.key
        lowest = min(r.base_m for r in mountains(key))
        assert (lowest < 1450) == bool(ALL_REGIONS[key].low_levels), key
        # Ground near sea level is read all the way down to 1000 hPa.
        assert (lowest < 320) == (ALL_REGIONS[key].low_levels[:1] == (1000,)), key


def test_close_neighbours_share_weather_within_their_region():
    found = {r.key: r for key in [*EAST, *CANADA] for r in mountains(key)}
    assert {key: r.weather_from for key, r in found.items() if r.weather_from} == SHARED
    for key, neighbour in SHARED.items():
        mine, theirs = found[key], found[neighbour]
        assert theirs.weather_from is None and theirs.region == mine.region and km(mine, theirs) < 8, key


def test_the_fifth_collector_sees_its_regions_and_plans_only_them():
    code = ("from tahoe_snow import config, usage; "
            "print(config.COLLECTOR, sorted(config.REGIONS), len(config.RESORTS), "
            "sum(usage.pulls(r) for r in config.REGIONS), round(usage.planned()))")
    out = subprocess.run([sys.executable, "-c", code], env={**os.environ, "SNOW_COLLECTOR": "east"}, text=True,
                         capture_output=True, check=True).stdout.strip()
    assert out.startswith(f"east {sorted(EAST)} 33 31 ")
    # 31 pulls twice a day; four of the five regions read five lower levels.
    assert 3700 < int(out.rsplit(" ", 1)[1]) < 4300
