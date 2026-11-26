"""The Tetons: eight places, their sensors, and the models fitted there instead of the Sierra's."""
import json

from tahoe_snow import biascorrect, calibrate, config, pipeline, usage
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS, ALL_STATIONS, MODELS, TETONS_BBOX, TETONS_STATIONS
from tahoe_snow.snow import observations, phase, ratio, train
from tahoe_snow.sources import omfiles_s3


def test_the_tetons_are_three_mountains_two_passes_and_three_classic_descents():
    places = {r.key: r for r in ALL_RESORTS.values() if r.region == "tetons"}
    classics = {"grandteton", "skillet", "middleteton"}
    assert set(places) == {"jacksonhole", "targhee", "snowking", "tetonpass", "togwotee"} | classics
    assert {k for k, r in places.items() if r.kind == "backcountry"} == {"tetonpass", "togwotee"} | classics
    # No sensor is within reach of the range's own peaks, and the Middle Teton shares the Grand's weather.
    assert all(places[key].station is None for key in classics)
    assert places["middleteton"].weather_from == "grandteton"
    for place in places.values():
        assert place.base_m < place.summit_m and place.base_m > 1450, place.key      # all above 850 hPa
    # Snow King has no sensor within reach; Teton Pass's sits below the pass, so it is a low sensor.
    assert places["snowking"].station is None and places["tetonpass"].weak_match
    for key in ("jacksonhole", "targhee", "togwotee"):
        assert places[key].station in TETONS_STATIONS and not places[key].weak_match, key


def test_the_tetons_are_built_at_the_wests_hours_on_their_own_clock_and_read_no_low_levels():
    region = ALL_REGIONS["tetons"]
    assert region.tz == "America/Denver" and region.at == ALL_REGIONS["tahoe"].at and region.low_levels == ()
    # The fifth collector builds them since the classic descents filled the first one's plan.
    assert region.collector == "east" and "tetons" not in config.REGIONS
    # Wyoming's SNOTEL days are stamped on the Pacific standard clock.
    assert region.std_offset_h == 8


def test_the_fitting_box_holds_every_teton_sensor():
    lat0, lat1, lon0, lon1 = TETONS_BBOX
    lats, lons, _, _ = omfiles_s3.grid_025(omfiles_s3.TETONS_BLOCK)
    for station in TETONS_STATIONS.values():
        assert lat0 < station.lat < lat1 and lon0 < station.lon < lon1, station.name
        assert lats[0] <= station.lat <= lats[-1] and lons[0] <= station.lon <= lons[-1], station.name
        assert ALL_STATIONS[station.triplet] is station
    assert calibrate.REGIONS["tetons"] == (TETONS_STATIONS, TETONS_BBOX, "tetons_daily")
    assert observations.BOXES["tetonbox"][:2] == (("WY", "ID"), TETONS_BBOX)
    assert train.REGION_BOXES["tetons"] == ("tetonbox", omfiles_s3.TETONS_BLOCK)


def test_a_box_takes_its_sensors_from_every_state_it_names(monkeypatch):
    listed = {"WY": [{"stationTriplet": "689:WY:SNTL", "name": "Phillips Bench", "latitude": 43.5169,
                      "longitude": -110.9126, "elevation": 8170.0},
                     {"stationTriplet": "1:WY:SNTL", "name": "Far Away", "latitude": 41.0, "longitude": -106.0,
                      "elevation": 9000.0}],
              "ID": [{"stationTriplet": "695:ID:SNTL", "name": "Pine Creek Pass", "latitude": 43.57,
                      "longitude": -111.2116, "elevation": 6710.0}]}
    monkeypatch.setattr(observations, "get_json", lambda kind, url, params: listed[params["stationTriplets"][2:4]])
    found = observations.box_stations(("WY", "ID"), TETONS_BBOX)
    assert set(found) == {"689:WY:SNTL", "695:ID:SNTL"} and round(found["689:WY:SNTL"].elev_m) == 2490
    assert set(observations.box_stations("WY", TETONS_BBOX)) == {"689:WY:SNTL"}


def test_the_tetons_use_their_own_correction_weights_split_and_ratio():
    correction = biascorrect.from_json(json.loads((MODELS / "bias_tetons.json").read_text()))
    for triplet in ("1082:WY:SNTL", "689:WY:SNTL", "822:WY:SNTL"):
        assert correction.fitted(triplet), triplet
    weights = pipeline.load_weights("tetons")
    assert weights == json.loads((MODELS / "weights_tetons.json").read_text())
    assert set(weights) == set(config.DET_MODELS) and abs(sum(weights.values()) - 1) < 0.005
    assert phase.params_file("tetons") == MODELS / "snow_phase_tetons.json"
    model, described = pipeline.load_snow_model("tetons")
    assert (model.phase_kind, model.phase_params) == phase.load("tetons")
    assert ratio.model_files("tetons")[0] == MODELS / "snow_ratio_tetons.joblib" and "Teton" in described
    # Every other region's ratio is still the Sierra's.
    for region in ("tahoe", "mammoth", "newengland", "seattle"):
        assert ratio.model_files(region)[0] == MODELS / "snow_ratio.joblib", region
        assert "Sierra" in pipeline.load_snow_model(region)[1], region
