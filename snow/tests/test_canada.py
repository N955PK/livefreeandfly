"""Canada's other regions so far, the second collector's: the BC Coast and Quebec."""
from tahoe_snow import config, usage
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS


def mountains(region: str) -> list:
    return [r for r in ALL_RESORTS.values() if r.region == region]


def test_the_bc_coast_runs_from_the_north_shore_to_the_duffey_and_across_to_the_island():
    region, found = ALL_REGIONS["bccoast"], mountains("bccoast")
    assert (region.collector, region.country, region.tz, region.low_levels) == ("canada", "Canada", "America/Vancouver", (950, 925, 900))
    assert len(found) == 8 and {r.key for r in found if r.kind == "backcountry"} == {"spearhead", "duffey", "paulridge"}
    for r in found:
        assert r.base_m < r.summit_m and r.station is None, r.key
        assert 49.3 < r.lat < 50.4 and -125.4 < r.lon < -122.4, r.key
        # Whistler's Creekside base, the lowest, is above the 950 hPa level.
        assert r.base_m > 540, r.key
    assert {r.key: r.weather_from for r in found if r.weather_from} == {"cypress": "grouse", "seymour": "grouse"}
    assert usage.pulls("bccoast", ALL_RESORTS) == 6


def test_quebec_is_three_clusters_built_at_new_englands_hours():
    region, found = ALL_REGIONS["quebec"], mountains("quebec")
    newengland = ALL_REGIONS["newengland"]
    assert (region.collector, region.country, region.tz) == ("canada", "Canada", "America/Toronto")
    assert (region.at, region.every_h, region.low_levels, region.std_offset_h) == (
        newengland.at, newengland.every_h, newengland.low_levels, newengland.std_offset_h)
    assert len(found) == 10 and all(r.kind == "resort" and r.station is None for r in found)
    for r in found:
        assert r.base_m < r.summit_m < 1450, r.key
        assert 45.0 < r.lat < 47.4 and -74.7 < r.lon < -70.5, r.key
    assert {r.key: r.weather_from for r in found if r.weather_from} == {"montblanc": "tremblant"}
    assert usage.pulls("quebec", ALL_RESORTS) == 9


def test_canadas_mountains_are_no_part_of_the_first_collectors_plan():
    canada = {key for key, region in ALL_REGIONS.items() if region.collector == "canada"}
    assert {"okanagan", "bccoast", "quebec"} <= canada and not canada & set(config.REGIONS)
    assert usage.planned() == usage.planned(config.REGIONS, config.RESORTS)
