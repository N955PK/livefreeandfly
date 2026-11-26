"""Colorado: nine resorts along I-70, at Winter Park and at Steamboat, and three passes, eight asking for weather."""
import json

from tahoe_snow import biascorrect, calibrate, config, pipeline, usage
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS, COLORADO_BBOX, COLORADO_STATIONS, MODELS
from tahoe_snow.snow import observations, phase, ratio, train
from tahoe_snow.sources import omfiles_s3


def test_the_colorado_mountains_are_where_they_should_be():
    found = [r for r in ALL_RESORTS.values() if r.region == "colorado"]
    assert len(found) == 14
    for r in found:
        assert r.base_m < r.summit_m, r.key
        # Ski Cooper in the south to Steamboat in the north, Beaver Creek in the west to Eldora in the east.
        assert 39.3 < r.lat < 40.5 and -106.9 < r.lon < -105.5, r.key
        assert r.station is None or r.station in config.COLORADO_STATIONS, r.key
        # Every base is far above the 850 hPa level, so the region reads no lower ones.
        assert r.base_m > 2000, r.key
    assert {r.key for r in found if r.kind == "backcountry"} == {"berthoud", "lovelandpass", "vailpass"}
    assert all(r.pass_group == "Backcountry" for r in found if r.kind == "backcountry")
    # Breckenridge's only sensor within reach is across the Tenmile Range, and the Lake Eldora sensor is not one
    # the region's correction was fitted to.
    assert [r.key for r in found if r.station is None] == ["breckenridge", "eldora"]
    assert config.levels_for("colorado") == config.PRESSURE_LEVELS


def test_eight_of_the_twelve_ask_for_weather():
    found = [r for r in ALL_RESORTS.values() if r.region == "colorado"]
    assert {r.key for r in found if r.weather_from is None} == {
        "vail", "beavercreek", "breckenridge", "keystone", "loveland", "copper", "winterpark", "steamboat",
        "eldora", "skicooper"}
    # Colorado is built by the third collector, so the first's plan no longer counts it.
    assert ALL_REGIONS["colorado"].collector == "west" and "colorado" not in config.REGIONS
    assert round(usage.planned({"colorado": ALL_REGIONS["colorado"]}, {r.key: r for r in found})) == round(
        10 * 3 * usage.CALLS_PER_RESORT_RUN)


def test_colorado_is_built_at_the_tetons_hours_and_reads_its_sensors_on_the_pacific_clock():
    region, tetons = ALL_REGIONS["colorado"], ALL_REGIONS["tetons"]
    assert (region.tz, region.at, region.every_h) == (tetons.tz, tetons.at, tetons.every_h)
    assert region.std_offset_h == 8
    assert region.avalanche == ("CAIC",)


def test_the_fitting_box_holds_every_colorado_sensor():
    lat0, lat1, lon0, lon1 = COLORADO_BBOX
    lats, lons, _, _ = omfiles_s3.grid_025(omfiles_s3.COLORADO_BLOCK)
    for station in COLORADO_STATIONS.values():
        assert lat0 < station.lat < lat1 and lon0 < station.lon < lon1, station.name
        assert lats[0] <= station.lat <= lats[-1] and lons[0] <= station.lon <= lons[-1], station.name
    assert calibrate.REGIONS["colorado"] == (COLORADO_STATIONS, COLORADO_BBOX, "colorado_daily")
    assert observations.BOXES["coloradobox"][:2] == ("CO", COLORADO_BBOX)
    assert train.REGION_BOXES["colorado"] == ("coloradobox", omfiles_s3.COLORADO_BLOCK)


def test_colorado_uses_its_own_correction_weights_split_and_ratio():
    correction = biascorrect.from_json(json.loads((MODELS / "bias_colorado.json").read_text()))
    # Every sensor has its own curve, the four above Steamboat among them.
    for triplet in COLORADO_STATIONS:
        assert correction.fitted(triplet), triplet
    weights = pipeline.load_weights("colorado")
    assert weights == json.loads((MODELS / "weights_colorado.json").read_text())
    assert set(weights) == set(config.DET_MODELS) and abs(sum(weights.values()) - 1) < 0.005
    model, described = pipeline.load_snow_model("colorado")
    assert (model.phase_kind, model.phase_params) == phase.load("colorado")
    assert phase.params_file("colorado") == MODELS / "snow_phase_colorado.json"
    assert ratio.model_files("colorado")[0] == MODELS / "snow_ratio_colorado.joblib" and "Colorado" in described
    # A Colorado snow day counts once: its days already outnumber the Sierra's.
    saved = json.loads((MODELS / "snow_ratio_colorado.json").read_text())
    assert "region_day_weight" not in saved and saved["region_events"] > saved["events"] / 2
    check = json.loads((MODELS / "snow_ratio_check_colorado.json").read_text())
    assert check["pooled_refit_each_station_held_out"]["snow_error_in"] < check["sierra_model"]["snow_error_in"]
