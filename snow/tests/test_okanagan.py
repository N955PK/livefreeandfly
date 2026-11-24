"""The Okanagan: Big White, SilverStar, Sun Peaks and Apex, the second collector's first region."""
from tahoe_snow import config, usage
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS


def test_the_okanagan_is_the_second_collectors_and_in_canada():
    region = ALL_REGIONS["okanagan"]
    assert (region.collector, region.country, region.tz) == ("canada", "Canada", "America/Vancouver")
    assert (region.at, region.every_h, region.low_levels) == ((5, 13, 21), 8, (900,))
    assert "okanagan" not in config.REGIONS and not any(r.region == "okanagan" for r in config.RESORTS.values())


def test_the_okanagan_mountains_are_where_they_should_be():
    found = [r for r in ALL_RESORTS.values() if r.region == "okanagan"]
    assert [r.key for r in found] == ["bigwhite", "silverstar", "sunpeaks", "apex"]
    for r in found:
        assert r.base_m < r.summit_m, r.key
        # Apex in the south to Sun Peaks in the north.
        assert 49.3 < r.lat < 51.0 and -120.0 < r.lon < -118.8, r.key
        assert r.station is None and r.weather_from is None and r.kind == "resort", r.key
    # SilverStar's and Sun Peaks' bases are under the 850 hPa level; the 900 hPa one is below them both.
    assert min(r.base_m for r in found) > 990


def test_four_pulls_three_times_a_day_with_the_extra_level():
    regions, resorts = {"okanagan": ALL_REGIONS["okanagan"]}, ALL_RESORTS
    per_pull = usage.CALLS_PER_RESORT_RUN + usage.EXTRA_LEVEL_CALLS
    assert usage.pulls("okanagan", resorts) == 4
    assert abs(usage.planned(regions, resorts) - 4 * 3 * per_pull) < 1e-6
