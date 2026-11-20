import json

import numpy as np
import pandas as pd

from tahoe_snow import biascorrect, blend, pipeline, powder
from tahoe_snow.config import RESORTS, STATIONS


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


def test_resort_without_a_station_gets_the_pooled_correction_and_no_observation():
    pairs = pd.concat([_pairs(bias=1.0, n=2000, station="big"), _pairs(bias=0.5, n=400, station="dry", seed=1)])
    correction = biascorrect.fit(pairs)
    values = np.array([10.0, 30.0])
    assert np.allclose(correction.apply("gfs", None, 1, values), correction.apply("gfs", "never_seen", 1, values))
    assert correction.fitted("dry") and not correction.fitted(None)
    mammoth = RESORTS["mammoth"]
    assert mammoth.station is None
    assert pipeline.water_correction(mammoth, correction) == "pooled"
    assert pipeline.water_correction(mammoth, None) is None
    hours = pd.date_range("2026-11-12", periods=48, freq="h")
    assert pipeline.observed(mammoth, hours[-1], hours) is None


def test_every_location_is_well_formed():
    assert {r.region for r in RESORTS.values()} == {"tahoe", "mammoth"}
    for resort in RESORTS.values():
        assert resort.kind in ("resort", "backcountry")
        assert (resort.pass_group == "Backcountry") == (resort.kind == "backcountry")
        assert resort.station is None or resort.station in STATIONS
        assert 1500 < resort.base_m < resort.summit_m < 3500
