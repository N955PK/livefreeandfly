"""Canada's other regions so far, the second collector's: the BC Coast and Quebec."""
from tahoe_snow import config, usage
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS


def mountains(region: str) -> list:
    return [r for r in ALL_RESORTS.values() if r.region == region]


def test_the_bc_coast_runs_from_the_north_shore_to_the_duffey_and_across_to_the_island():
    region, found = ALL_REGIONS["bccoast"], mountains("bccoast")
    assert (region.collector, region.country, region.tz, region.low_levels) == (
        "canada", "Canada", "America/Vancouver", (1000, 975, 950, 925, 900))
    assert len(found) == 12 and {r.key for r in found if r.kind == "backcountry"} == {
        "spearhead", "duffey", "paulridge", "mtcurrie", "joffre"}
    for r in found:
        assert r.base_m < r.summit_m, r.key
        # Manning Park, in the Cascades 150 km east of the North Shore, and Sasquatch were added later.
        assert 49.0 < r.lat < 50.4 and -125.4 < r.lon < -120.9, r.key
        # Mt. Currie's start on the Pemberton valley floor, the lowest, is above the 1000 hPa level.
        assert r.base_m > 110, r.key
    assert {r.key: r.weather_from for r in found if r.weather_from} == {"cypress": "grouse", "seymour": "grouse",
                                                                         "joffre": "duffey"}
    assert usage.pulls("bccoast", ALL_RESORTS) == 9


def test_quebec_is_three_clusters_built_at_new_englands_hours():
    region, found = ALL_REGIONS["quebec"], mountains("quebec")
    newengland = ALL_REGIONS["newengland"]
    # The fifth collector builds Quebec since the classic descents filled the second one's plan.
    assert (region.collector, region.country, region.tz) == ("east", "Canada", "America/Toronto")
    assert (region.at, region.every_h, region.low_levels, region.std_offset_h) == (
        newengland.at, newengland.every_h, newengland.low_levels, newengland.std_offset_h)
    assert len(found) == 12 and all(r.kind == "resort" and r.station is None for r in found)
    for r in found:
        assert r.base_m < r.summit_m < 1450, r.key
        # Mont-Édouard and Le Valinouët, in the Saguenay, were added later.
        assert 45.0 < r.lat < 48.8 and -74.7 < r.lon < -70.2, r.key
    assert {r.key: r.weather_from for r in found if r.weather_from} == {"montblanc": "tremblant"}
    assert usage.pulls("quebec", ALL_RESORTS) == 11


def test_canadas_mountains_are_no_part_of_the_first_collectors_plan():
    canada = {key for key, region in ALL_REGIONS.items() if region.collector == "canada"}
    assert {"okanagan", "bccoast", "rockies"} <= canada and not canada & set(config.REGIONS)
    assert usage.planned() == usage.planned(config.REGIONS, config.RESORTS)


def test_the_powder_highway_is_two_regions_because_it_keeps_two_clocks():
    west, east = ALL_REGIONS["powderhighway"], ALL_REGIONS["eastkootenays"]
    assert (west.tz, east.tz) == ("America/Vancouver", "America/Edmonton")
    assert all(region.collector == "canada" and region.country == "Canada" for region in (west, east))
    assert [r.key for r in mountains("powderhighway")] == [
        "revelstoke", "redmountain", "whitewater", "rogerspass", "kootenaypass", "comstock", "sevensteps"]
    assert [r.key for r in mountains("eastkootenays")] == ["kickinghorse", "panorama", "kimberley", "fernie",
                                                             "castlemountain"]
    for r in mountains("powderhighway") + mountains("eastkootenays"):
        assert r.base_m < r.summit_m and r.weather_from is None, r.key
    # Revelstoke's base is under the 950 hPa level, so the west reads down to 975; the east's lowest is Fernie's.
    assert west.low_levels == (975, 950, 925, 900) and min(r.base_m for r in mountains("powderhighway")) > 320
    assert east.low_levels == (900,) and min(r.base_m for r in mountains("eastkootenays")) > 990


def test_the_rockies_are_seven_mountains_and_four_classic_descents_on_albertas_clock():
    region, found = ALL_REGIONS["rockies"], mountains("rockies")
    assert (region.tz, region.std_offset_h, region.collector, region.country) == ("America/Edmonton", 7, "canada", "Canada")
    assert [r.key for r in found] == [
        "lakelouise", "sunshine", "norquay", "nakiska", "marmot", "bowsummit", "parkerridge", "robson", "aemmer",
        "mtcolumbia", "skyladder"]
    assert all(r.base_m < r.summit_m and r.weather_from is None for r in found)
    # Mt. Robson's start by the Robson River, at 849 m, is the only ground under 1,450 m: it is above the 925 hPa level.
    assert region.low_levels == (925, 900) and min(r.base_m for r in found) > 760
    assert usage.pulls("rockies", ALL_RESORTS) == 11
