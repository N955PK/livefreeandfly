"""The Wasatch: nine resorts and three backcountry peaks above Salt Lake City, six asking for their own weather."""
from tahoe_snow import config, pipeline, usage
from tahoe_snow.config import RESORTS


def test_the_wasatch_mountains_are_where_they_should_be():
    found = config.resorts_in("wasatch")
    assert len(found) == 12
    for r in found:
        assert r.base_m < r.summit_m, r.key
        # Sundance and Mt. Timpanogos in the south to Powder Mountain in the north.
        assert 40.3 < r.lat < 41.5 and -112.0 < r.lon < -111.4, r.key
        assert r.station is None or r.station in config.WASATCH_STATIONS, r.key
        # Every base is above the 850 hPa level, so the region reads no lower ones.
        assert r.base_m > 1450, r.key
    assert {r.key for r in found if r.kind == "backcountry"} == {"superior", "cardiff", "timpanogos"}
    assert all(r.pass_group == "Backcountry" for r in found if r.kind == "backcountry")
    assert [r.key for r in found if r.station is None] == ["snowbasin"]
    assert config.levels_for("wasatch") == config.PRESSURE_LEVELS


def test_six_of_the_twelve_ask_for_weather():
    assert usage.pulls("wasatch") == 6
    assert {r.key for r in config.resorts_in("wasatch") if r.weather_from is None} == {
        "alta", "brighton", "parkcity", "snowbasin", "powdermountain", "sundance"}
    assert round(usage.planned({"wasatch": config.REGIONS["wasatch"]})) == round(6 * 3 * usage.CALLS_PER_RESORT_RUN)
    assert usage.planned() <= usage.PLAN_LIMIT


def test_the_wasatch_is_built_at_the_tetons_hours_and_reads_its_sensors_on_the_pacific_clock():
    region, tetons = config.REGIONS["wasatch"], config.REGIONS["tetons"]
    assert (region.tz, region.at, region.every_h) == (tetons.tz, tetons.at, tetons.every_h)
    assert pipeline.snotel_offset_h(RESORTS["alta"]) == 8
    assert region.avalanche == ("UAC",)
