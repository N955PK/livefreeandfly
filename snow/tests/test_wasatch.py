"""The Wasatch: nine resorts and three backcountry peaks above Salt Lake City, six asking for their own weather."""
import json

import pandas as pd

from tahoe_snow import calibrate, config, pipeline, usage
from tahoe_snow.config import MODELS, RESORTS, WASATCH_BBOX, WASATCH_STATIONS
from tahoe_snow.snow import observations, phase, ratio, train
from tahoe_snow.sources import omfiles_s3


def test_the_wasatch_mountains_are_where_they_should_be():
    found = config.resorts_in("wasatch")
    assert len(found) == 14
    for r in found:
        assert r.base_m < r.summit_m, r.key
        # Sundance and Mt. Timpanogos in the south to Powder Mountain in the north.
        assert 40.3 < r.lat < 41.5 and -112.0 < r.lon < -111.4, r.key
        assert r.station is None or r.station in config.WASATCH_STATIONS, r.key
        # Every base is above the 850 hPa level, so the region reads no lower ones.
        assert r.base_m > 1450, r.key
    assert {r.key for r in found if r.kind == "backcountry"} == {"superior", "cardiff", "timpanogos", "hypodermicneedle",
                                                              "coldfusion"}
    assert all(r.pass_group == "Backcountry" for r in found if r.kind == "backcountry")
    assert [r.key for r in found if r.station is None] == ["snowbasin"]
    assert config.levels_for("wasatch") == config.PRESSURE_LEVELS


def test_six_of_the_twelve_ask_for_weather():
    assert usage.pulls("wasatch") == 7
    assert {r.key for r in config.resorts_in("wasatch") if r.weather_from is None} == {
        "alta", "brighton", "parkcity", "snowbasin", "powdermountain", "sundance", "coldfusion"}
    assert round(usage.planned({"wasatch": config.REGIONS["wasatch"]})) == round(7 * 3 * usage.CALLS_PER_RESORT_RUN)


def test_the_wasatch_is_built_at_the_tetons_hours_and_reads_its_sensors_on_the_pacific_clock():
    region, tetons = config.REGIONS["wasatch"], config.ALL_REGIONS["tetons"]
    assert (region.tz, region.at, region.every_h) == (tetons.tz, tetons.at, tetons.every_h)
    assert pipeline.snotel_offset_h(RESORTS["alta"]) == 8
    assert region.avalanche == ("UAC",)


def test_the_fitting_box_holds_every_wasatch_sensor():
    lat0, lat1, lon0, lon1 = WASATCH_BBOX
    lats, lons, _, _ = omfiles_s3.grid_025(omfiles_s3.WASATCH_BLOCK)
    for station in WASATCH_STATIONS.values():
        assert lat0 < station.lat < lat1 and lon0 < station.lon < lon1, station.name
        assert lats[0] <= station.lat <= lats[-1] and lons[0] <= station.lon <= lons[-1], station.name
    assert calibrate.REGIONS["wasatch"] == (WASATCH_STATIONS, WASATCH_BBOX, "wasatch_daily")
    assert observations.BOXES["wasatchbox"][:2] == ("UT", WASATCH_BBOX)
    assert train.REGION_BOXES["wasatch"] == ("wasatchbox", omfiles_s3.WASATCH_BLOCK)


def test_the_wasatch_uses_its_own_correction_weights_split_and_ratio():
    correction = pipeline.load_corrections()["wasatch"]
    for triplet in WASATCH_STATIONS:
        assert correction.fitted(triplet), triplet
    weights = pipeline.load_weights("wasatch")
    assert weights == json.loads((MODELS / "weights_wasatch.json").read_text())
    assert set(weights) == set(config.DET_MODELS) and abs(sum(weights.values()) - 1) < 0.005
    model, described = pipeline.load_snow_model("wasatch")
    assert (model.phase_kind, model.phase_params) == phase.load("wasatch")
    # The line between rain and snow sits lower than the Sierra's.
    assert model.phase_params["center_c"] < phase.load()[1]["center_c"]
    assert ratio.model_files("wasatch")[0] == MODELS / "snow_ratio_wasatch.joblib" and "Wasatch" in described


def test_a_wasatch_snow_day_counts_ten_times_in_its_ratio_and_a_teton_one_once():
    days = pd.DataFrame({"liquid_mm": [5.0, 9.0]})
    assert train.pooled_weights(3, days, "wasatch").tolist() == [1, 1, 1, 10, 10]
    assert train.pooled_weights(3, days, "tetons").tolist() == [1, 1, 1, 1, 1]
    saved = json.loads((MODELS / "snow_ratio_wasatch.json").read_text())
    assert saved["region_day_weight"] == 10 and saved["where"] == "Sierra and Wasatch"
    # The check kept beside the model: the one in use beats the Sierra's at stations held out.
    check = json.loads((MODELS / "snow_ratio_check_wasatch.json").read_text())
    assert check["pooled_refit_each_station_held_out"]["snow_error_in"] < check["sierra_model"]["snow_error_in"]
