import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from tahoe_snow import biascorrect, blend, calibrate, pipeline, powder, season, usage
from tahoe_snow.config import ALL_STATIONS, RESORTS
from tahoe_snow.sources import cdec, nv511, openmeteo, snotel


def _pairs(bias=1.0, n=400, station="a", seed=0, model="gfs", lead=1):
    rng = np.random.default_rng(seed)
    observed = np.where(rng.random(n) < 0.4, rng.gamma(1.2, 15.0, n), 0.0)
    return pd.DataFrame({"model": model, "station": station, "lead_day": lead,
                         "forecast_mm": observed * bias, "observed_mm": observed})


def test_identity_when_forecast_equals_observation():
    pairs = _pairs()
    correction = biascorrect.fit(pairs)
    values = np.array([0.0, 2.0, 10.0, 40.0, 0.98 * pairs["observed_mm"].max()])
    assert np.allclose(correction.apply("gfs", "a", 1, values), values, rtol=0.03, atol=0.2)


def test_dry_model_is_corrected_including_beyond_training_range():
    pairs = _pairs(bias=0.7)
    correction = biascorrect.fit(pairs)
    record = pairs["observed_mm"].max()
    # The last value is above anything the model produced in training, but below the record once corrected.
    values = np.array([7.0, 28.0, 0.69 * record])
    corrected = correction.apply("gfs", "a", 1, values)
    assert np.allclose(corrected, values / 0.7, rtol=0.05)


def test_thin_station_falls_back_toward_pooled():
    pairs = pd.concat([_pairs(bias=1.0, n=2000, station="big"), _pairs(bias=0.5, n=40, station="thin", seed=1)])
    correction = biascorrect.fit(pairs, min_wet_days=40)
    out = correction.apply("gfs", "thin", 1, np.array([10.0]))[0]
    # Alone the thin station would double the value; pooled leaves it near 10.
    assert 11.0 < out < 17.0
    assert abs(correction.apply("gfs", "never_seen", 1, np.array([10.0]))[0] - 10.6) < 1.5


def test_unfitted_model_passes_through_and_nan_stays_nan():
    correction = biascorrect.fit(_pairs())
    assert np.allclose(correction.apply("other", "a", 1, np.array([3.0])), [3.0])
    assert np.isnan(correction.apply("gfs", "a", 1, np.array([np.nan]))[0])


def test_longer_leads_use_longest_fitted_lead_and_json_round_trip():
    pairs = pd.concat([_pairs(bias=1.0, lead=1), _pairs(bias=0.5, lead=3, seed=2)])
    correction = biascorrect.from_json(json.loads(json.dumps(biascorrect.to_json(biascorrect.fit(pairs)))))
    assert abs(correction.apply("gfs", "a", 7, np.array([10.0]))[0] - 20.0) < 2.0
    assert abs(correction.factor("gfs", "a", 3, np.array([10.0, 0.0]))[0] - 2.0) < 0.2
    assert correction.factor("gfs", "a", 3, np.array([10.0, 0.0]))[1] == 1.0


def test_weighted_mean_skips_missing_models():
    frame = pd.DataFrame({"a": [10.0, np.nan, np.nan], "b": [20.0, 20.0, np.nan]})
    out = blend.weighted_mean(frame, {"a": 3.0, "b": 1.0})
    assert out[0] == 12.5 and out[1] == 20.0 and np.isnan(out[2])


def test_member_stats_ordered_and_bounded():
    rng = np.random.default_rng(0)
    members = pd.DataFrame(rng.gamma(2.0, 10.0, size=(5, 60)))
    members.iloc[4, 5:] = np.nan
    stats = blend.member_stats(members)
    ok = stats.iloc[:4]
    assert (ok["p10_cm"] <= ok["p50_cm"]).all() and (ok["p50_cm"] <= ok["p90_cm"]).all()
    assert ok[["prob_6in", "prob_12in"]].stack().between(0, 1).all()
    assert (ok["prob_12in"] <= ok["prob_6in"]).all()
    assert np.isnan(stats["p50_cm"].iloc[4]) and np.isnan(stats["prob_6in"].iloc[4])


def test_local_day_totals_need_complete_days():
    index = pd.date_range("2026-01-01 08:00", periods=40, freq="h")
    totals = blend.local_day_totals(pd.DataFrame({"snow": 1.0}, index=index))
    assert totals.loc["2026-01-01", "snow"] == 24.0
    assert np.isnan(totals.loc["2026-01-02", "snow"])


def test_powder_score_cases():
    assert powder.score(powder.DayPart(snow_in=0.0, slr=10.0)) == 0.0
    assert powder.score(powder.DayPart(snow_in=float("nan"), slr=10.0)) == 0.0
    great = powder.score(powder.DayPart(snow_in=12, slr=15, ridge_wind_mph=8, overnight_share=1.0))
    assert great > 8.0
    heavy_windy = powder.score(powder.DayPart(snow_in=12, slr=7, ridge_wind_mph=50, overnight_share=1.0))
    assert heavy_windy < 0.5 * great
    rained_on = powder.score(powder.DayPart(snow_in=12, slr=15, rain_share=0.3, late_rain_mm=5.0))
    assert rained_on < 0.55 * great
    assert powder.score(powder.DayPart(snow_in=60, slr=15, slr_change=3, overnight_share=1.0)) <= 10.0


def test_corrected_water_never_exceeds_the_station_record():
    pairs = _pairs(bias=0.15, n=600)
    correction = biascorrect.from_json(json.loads(json.dumps(biascorrect.to_json(biascorrect.fit(pairs)))))
    record = pairs["observed_mm"].max()
    out = correction.apply("gfs", "a", 0, np.array([0.5 * record, 5.0, np.nan]))
    assert out[0] <= record + 1e-9          # uncapped this would be several times the record
    assert abs(out[1] - 5.0 / 0.15) < 6.0   # ordinary days are still corrected
    assert np.isnan(out[2])


def test_robust_mean_ignores_one_runaway_model():
    index = pd.date_range("2026-01-02 08:00", periods=24, freq="h")
    frame = pd.DataFrame({"a": 1.0, "b": 1.2, "c": 0.8, "runaway": 9.0}, index=index)
    assert abs(blend.robust_mean(frame).sum() - 24 * 1.1) < 1e-6      # the median of 24, 28.8, 19.2, 216 is 26.4
    assert abs(blend.weighted_mean(frame).sum() - 24 * 3.0) < 1e-6
    calm = pd.DataFrame({"a": 1.0, "b": 1.0}, index=index)
    assert np.allclose(blend.robust_mean(calm), 1.0)


def test_resort_without_a_station_is_left_uncorrected_and_has_no_observation():
    pairs = pd.concat([_pairs(bias=1.0, n=2000, station="big"), _pairs(bias=0.5, n=400, station="dry", seed=1)])
    correction = biascorrect.fit(pairs)
    assert correction.fitted("dry") and not correction.fitted(None)
    june = RESORTS["june"]
    assert june.station is None
    assert pipeline.water_correction(june, correction) is None
    assert pipeline.water_correction(RESORTS["mammoth"], None) is None
    index = pd.date_range("2026-01-02 08:00", periods=48, freq="h")
    precip = pd.Series(1.0, index=index)
    today = pd.Timestamp("2026-01-02")
    assert pipeline.corrected_liquid(precip, "gfs", None, today, correction, "America/Los_Angeles").equals(precip)
    assert not np.allclose(pipeline.corrected_liquid(precip, "gfs", "dry", today, correction, "America/Los_Angeles"), precip)
    assert pipeline.observed(june, index[-1], index) is None


def test_cdec_daily_rows_are_dated_like_snotel_and_converted(monkeypatch):
    payload = [{"SENSOR_NUM": 3, "date": f"2026-01-{day:02d} 00:00", "value": value}
               for day, value in [(10, 1.0), (11, 1.0), (12, 2.5), (13, -9999)]]
    payload.append({"SENSOR_NUM": 18, "date": "2026-01-12 00:00", "value": 30})
    frame = cdec.parse(payload, cdec.DAILY_SENSORS)
    assert abs(frame.loc["2026-01-12", "swe_mm"] - 63.5) < 1e-9
    assert abs(frame.loc["2026-01-12", "depth_cm"] - 76.2) < 1e-9
    assert pd.Timestamp("2026-01-13") not in frame.index
    # CDEC's value dated the 12th was read at the midnight that starts the 12th, so it closes out the 11th.
    monkeypatch.setattr(cdec, "_fetch", lambda *args: payload)
    gains = snotel.daily_gains(cdec.daily("MHP", "2026-01-10", "2026-01-13"))
    assert abs(gains.loc["2026-01-11", "swe_gain_mm"] - 38.1) < 1e-9


def test_pillow_gains_ignore_jitter_and_spikes_but_keep_storms():
    days = pd.date_range("2026-01-01", periods=14)
    # Quiet, jitter, a two-day storm, a one-day spike, a real loss of 11 mm, then more snow.
    swe = pd.Series([100.0, 100, 103, 99, 101, 131, 151, 151, 400, 151, 140, 140, 160, 160], index=days)
    gains = cdec.pillow_gains(swe)
    assert abs(gains.sum() - (151 - 100 + 160 - 145)) < 3      # the two storms, give or take the jitter
    assert gains.max() <= 31                                      # the 400 mm spike is not a storm
    assert gains.loc["2026-01-06"] > 20 and gains.loc["2026-01-13"] == 15
    gap = swe.copy()
    gap.iloc[5:7] = np.nan
    assert cdec.pillow_gains(gap).reindex(days[5:8]).isna().all()   # no gain is credited across missing days


def test_phantom_station_days_are_dropped():
    days = pd.date_range("2026-01-01", periods=6)
    table = pd.DataFrame({"model": "gfs", "station": "a", "date": days,
                          "forecast_mm": [0.0, 0.0, 0.0, 0.0, 30.0, 0.0],
                          "observed_mm": [0.0, 60.0, 0.0, 40.0, 35.0, 30.0]})
    kept = calibrate.without_phantoms(table)
    # The 2nd is a sensor step (no model had anything near it); the 4th and 6th sit beside a real storm day.
    assert list(kept["date"].dt.day) == [1, 3, 4, 5, 6]


def test_observed_reports_water_when_the_sensor_has_no_depth(monkeypatch):
    hours = pd.date_range("2026-01-01", periods=96, freq="h")
    now = hours[-1]
    pst = pd.date_range(hours[0] - pd.Timedelta(hours=40), periods=140, freq="h")
    frame = pd.DataFrame({"swe_mm": np.linspace(100.0, 200.0, len(pst)), "depth_cm": 43.2, "tobs_c": -5.0}, index=pst)
    monkeypatch.setattr(cdec, "hourly", lambda *args, **kwargs: frame)
    out = pipeline.observed(RESORTS["mammoth"], now, hours)
    assert out["station"] == "Mammoth Pass" and out["depth_in"] is None and out["depth_gain_72h_in"] is None
    assert out["water_in"] is not None and out["water_gain_72h_in"] > out["water_gain_24h_in"] > 0
    assert out["temp_f"] == 23


def test_every_location_is_well_formed():
    assert {r.region for r in RESORTS.values()} == {"tahoe", "mammoth", "newengland"}
    for resort in RESORTS.values():
        assert resort.kind in ("resort", "backcountry")
        assert (resort.pass_group == "Backcountry") == (resort.kind == "backcountry")
        assert resort.station is None or resort.station in ALL_STATIONS
        floor = 0 if resort.region == "newengland" else 1500     # the Sierra's lowest base sits above 1,500 m
        assert floor < resort.base_m < resort.summit_m < 4500


def test_call_weight_follows_the_published_examples():
    variables = ",".join(f"v{n}" for n in range(15))
    two_weeks = {"hourly": variables, "models": "gfs_seamless", "forecast_days": 14}
    assert openmeteo.call_weight(openmeteo.FORECAST_URL, two_weeks) == 1.5
    assert openmeteo.call_weight(openmeteo.FORECAST_URL, {**two_weeks, "forecast_days": 28}) == 3.0
    assert openmeteo.call_weight(openmeteo.FORECAST_URL, {"hourly": "precipitation", "forecast_days": 3}) == 1.0
    members = {"hourly": "precipitation,temperature_2m", "models": "ecmwf_ifs025", "forecast_days": 10}
    assert openmeteo.call_weight(openmeteo.ENSEMBLE_URL, members) == 10.2


def test_usage_ledger_totals_the_last_day_and_month(tmp_path):
    now = datetime(2026, 11, 20, 12)
    path = tmp_path / "usage.json"
    requests = [(openmeteo.FORECAST_URL, {"hourly": "precipitation", "forecast_days": 28}, "ok", None),
                (openmeteo.FORECAST_URL, {"hourly": "precipitation"}, "limited", None),
                ("https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data", {}, "ok", None)]
    run = usage.of_run(requests)
    assert run == {"requests": 1, "calls": 2.0, "by_rule": 2.0, "measured": False, "rate_limited": 1}
    charged = usage.of_run([(openmeteo.FORECAST_URL, {"hourly": "precipitation", "forecast_days": 28}, "ok", 1.4)])
    assert (charged["calls"], charged["by_rule"], charged["measured"]) == (1.4, 2.0, True)
    for hours_ago in (40 * 24, 36, 3):
        ledger = usage.record(run, now - timedelta(hours=hours_ago), path)
    ledger = usage.record(run, now, path)
    assert len(ledger) == 3
    use = usage.summary(ledger, now)
    assert (use["calls_24h"], use["runs_24h"], use["calls_30d"], use["rate_limited_24h"]) == (4, 2, 6, 2)


def test_nevada_road_status_keeps_restricted_stretches_inside_the_maps():
    line = ["_y|mFbe{yUg~Ag~A"]
    rows = [
        {"RoadwayName": "SR-431", "Overall Status": "Chains or Snow Tires Required", "EncodedPolyline": line,
         "LocationDescription": "from NV-28 to I-580", "LastUpdated": 1},
        {"RoadwayName": "US-50", "Overall Status": "No Restrictions", "EncodedPolyline": line},
    ]
    events = [
        {"RoadwayName": "NV-207", "IsFullClosure": True, "Latitude": 38.98, "Longitude": -119.89},
        {"RoadwayName": "NV-28", "IsFullClosure": False, "Latitude": 39.2, "Longitude": -119.93},
        {"RoadwayName": "US-95", "IsFullClosure": True, "Latitude": 36.2, "Longitude": -115.1},
    ]
    status = nv511.build(rows, events, pd.Timestamp("2026-11-20T16:00Z").to_pydatetime())
    assert nv511.decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    assert [(row["route"], row["status"]) for row in status["rows"]] == [("NV-431", "chains"), ("NV-207", "closed")]
    assert {point["route"] for point in status["points"]} == {"NV-431", "NV-207"}
    assert status["updated"] == "2026-11-20T16:00:00Z"


def test_season_normal_is_the_median_of_past_years_on_this_date():
    days = pd.date_range("2000-10-01", "2026-11-20", freq="D")
    into_year = (days - pd.to_datetime((season.water_year(days) - 1).astype(str) + "-10-01")).days
    # Every year climbs to its peak on day 180 and melts by day 270; odd years carry twice the snow of even ones.
    shape = np.clip(np.minimum(into_year / 180, (270 - into_year) / 90), 0, None)
    swe = pd.Series(shape * np.where(season.water_year(days) % 2, 40.0, 20.0), index=days)
    normal = season.from_history(swe, pd.Timestamp("2026-11-20"))
    assert normal["years"] == 26
    assert abs(normal["peak_in"] - 30.0) < 0.5
    # The five-day smoothing flattens the top, and the first day of the plateau counts as the peak.
    assert normal["peak_date"] in {"03-28", "03-29", "03-30"}
    assert abs(normal["normal_in"] - 30.0 * 50 / 180) < 0.5
    told = season.summary({"depth_in": 4.2}, {"depth": normal})["depth"]
    assert told["pct_peak"] == 14 and told["pct_normal"] == round(100 * 4.2 / normal["normal_in"])
    assert season.summary({"water_in": 4.2}, {"water": {**normal, "normal_in": 0.4}})["water"]["pct_normal"] is None
    assert season.summary({"depth_in": None, "water_in": 4.2}, {"depth": normal}) is None
    # Snowfall is water gained on cold days times a snow ratio, added up from October 1; a warm day's gain is rain.
    days = pd.date_range("2026-10-01", periods=8, freq="D")
    frame = pd.DataFrame({"swe_mm": [0.0, 0.0, 25.4, 50.8, 76.2, 76.2, 76.2, 76.2],
                          "tavg_c": [5.0, 5.0, -1.0, -9.0, 4.0, 0.0, 0.0, 0.0]}, index=days)
    assert season.snowfall_in(frame).round(1).tolist() == [0.0, 8.0, 22.0, 22.0, 22.0, 22.0, 22.0]
    curve = normal["curve"]
    assert sorted(curve["years"]) == [str(year) for year in range(2017, 2028)]
    # The most ever on a date is an odd winter's reading, since they carry twice the snow.
    assert abs(curve["high"]["values"][60] - 40.0) < 0.5 and curve["high"]["years"][60] % 2 == 1
    # Odd winters are the big ones and all alike, so the latest of them holds the record.
    assert curve["record"]["year"] == "2025" and 37.0 < max(curve["record"]["values"]) <= 40.0
    assert len(curve["normal"]) == len(curve["years"]["2026"]) == 122 and abs(curve["normal"][60] - 30.0) < 0.5
    # This winter has run 50 days, so its line stops there.
    assert curve["years"]["2027"][16] is not None and curve["years"]["2027"][18] is None


def test_a_run_waits_for_room_only_once_the_service_has_refused_or_it_was_started_by_hand():
    now = datetime(2026, 11, 21, 1, 0)

    def ledger(runs, refused=0):
        return [{"utc": (now - timedelta(hours=hour + 1)).strftime(usage.STAMP), "calls": 970.0,
                 "rate_limited": refused, "measured": True} for hour in range(runs)]

    assert usage.room(ledger(3), now, by_hand=False)[0] and usage.room(ledger(3), now, by_hand=True)[0]
    # Ten runs fill the day: a scheduled run still goes while nothing has been refused, one started by hand does not.
    assert usage.room(ledger(10), now, by_hand=False)[0] and not usage.room(ledger(10), now, by_hand=True)[0]
    assert not usage.room(ledger(10, refused=4), now, by_hand=False)[0]
    assert usage.room([], now, by_hand=True)[0]


def test_one_unreadable_sensor_does_not_cost_the_others_their_season(monkeypatch):
    from tahoe_snow import season

    bad = sorted({resort.station for resort in season.RESORTS.values() if resort.station})[0]

    def fake(station, day):
        if station.name == season.ALL_STATIONS[bad].name:
            raise ValueError("Expecting value: line 1 column 2 (char 1)")
        return {"water": {"curve": {}}}

    monkeypatch.setattr(season, "station_normal", fake)
    found = season.normals(pd.Timestamp("2026-11-21T16:00:00Z"))
    assert found[season.ALL_STATIONS[bad].triplet] == {}
    assert all(normal for triplet, normal in found.items() if triplet != season.ALL_STATIONS[bad].triplet)
    assert len(found) > 1

