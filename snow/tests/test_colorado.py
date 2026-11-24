"""Colorado: nine resorts along I-70, at Winter Park and at Steamboat, and three passes, eight asking for weather."""
from tahoe_snow import config, pipeline, usage
from tahoe_snow.config import RESORTS


def test_the_colorado_mountains_are_where_they_should_be():
    found = config.resorts_in("colorado")
    assert len(found) == 12
    for r in found:
        assert r.base_m < r.summit_m, r.key
        # Breckenridge in the south to Steamboat in the north, Beaver Creek in the west to Winter Park in the east.
        assert 39.4 < r.lat < 40.5 and -106.9 < r.lon < -105.7, r.key
        assert r.station is None or r.station in config.COLORADO_STATIONS, r.key
        # Every base is far above the 850 hPa level, so the region reads no lower ones.
        assert r.base_m > 2000, r.key
    assert {r.key for r in found if r.kind == "backcountry"} == {"berthoud", "lovelandpass", "vailpass"}
    assert all(r.pass_group == "Backcountry" for r in found if r.kind == "backcountry")
    # Breckenridge's only sensor within reach is across the Tenmile Range.
    assert [r.key for r in found if r.station is None] == ["breckenridge"]
    assert config.levels_for("colorado") == config.PRESSURE_LEVELS


def test_eight_of_the_twelve_ask_for_weather():
    assert usage.pulls("colorado") == 8
    assert {r.key for r in config.resorts_in("colorado") if r.weather_from is None} == {
        "vail", "beavercreek", "breckenridge", "keystone", "loveland", "copper", "winterpark", "steamboat"}
    assert round(usage.planned({"colorado": config.REGIONS["colorado"]})) == round(8 * 3 * usage.CALLS_PER_RESORT_RUN)
    # Colorado took the plan past the old ceiling of 8,500; the service allows 10,000.
    assert 8500 < usage.planned() <= usage.PLAN_LIMIT < 10000


def test_colorado_is_built_at_the_tetons_hours_and_reads_its_sensors_on_the_pacific_clock():
    region, tetons = config.REGIONS["colorado"], config.REGIONS["tetons"]
    assert (region.tz, region.at, region.every_h) == (tetons.tz, tetons.at, tetons.every_h)
    assert pipeline.snotel_offset_h(RESORTS["vail"]) == 8
    assert region.avalanche == ("CAIC",)
