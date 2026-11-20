# Tahoe Snow Forecast Implementation Plan

**Goal:** A free, verified snow forecast for Tahoe resorts whose snow model
(snow ratio, rain/snow split, snowfall) is trained and tested on measured data.

**Architecture:** A Python package fetches free forecasts and station
observations, converts corrected liquid to snowfall through a trained snow
model, blends models and ensembles, and writes JSON that a static site reads.
A scoring job compares archived forecasts with stations.

**Tech stack:** Python 3.11, numpy, pandas, scipy, scikit-learn, requests,
pyarrow, pytest. Static HTML/JS (no framework). GitHub Actions + Pages later.

**Spec:** `docs/2026-11-19-tahoe-snow-design.md`. Sean's addition on approval:
do not cut corners on the snow model; it is the most important part.

## Global constraints

- No API keys, no paid services, no ads. Generic user agent, no personal data.
- Open-Meteo: stay under 600 calls/min, 5,000/h, 10,000/day; cache every raw
  response on disk and never refetch what is cached.
- No resort-reported snowfall. No OpenSnow data.
- A trained component ships only if it beats its simple baseline on held-out
  seasons; otherwise the baseline ships and the site says so.
- Nothing is pushed to GitHub without Sean's go-ahead.
- Imports at the top of files; flake8, 120 columns; American spelling.

## Review focus

1. A model returns nulls for a variable (IFS has no freezing level, NBM no
   pressure levels): the pipeline skips that model for that quantity, never
   crashes or treats null as zero.
2. Station gaps and sensor glitches (negative SWE steps, depth spikes): events
   are dropped by quality rules, not turned into absurd snow ratios.
3. Rain or mixed days: snowfall goes to zero smoothly below the snow level;
   no snow reported at 5 °C wet-bulb.
4. Tiny liquid amounts (under 2.5 mm): excluded from ratio training and
   scoring, since ratio error explodes.
5. A whole source is down at run time: the run uses the last cached data,
   marks the page stale, and exits nonzero only if nothing can be produced.

---

## Files

```
tahoe_snow/
  config.py        resorts, stations, model names, paths
  cache.py         fetch-with-disk-cache helper
  sources/openmeteo.py   forecast, ensemble, historical-forecast, previous-runs
  sources/snotel.py      hourly and daily SNWD, WTEQ, PREC, TOBS
  sources/ghcn.py        daily SNOW, PRCP, TMAX, TMIN, WESF (COOP + CoCoRaHS)
  sources/narr.py        reanalysis profiles at a point (PSL THREDDS)
  physics.py       wet-bulb, profile interpolation, snow level, Kuchera
  snow/dataset.py  build training tables (events + predictors)
  snow/ratio.py    snow-ratio models, cross-validation, selection
  snow/phase.py    snow-fraction model
  snow/model.py    liquid + profile -> snowfall (the shipped snow model)
  biascorrect.py   quantile mapping with pooled shrinkage
  blend.py         model weights, ensemble percentiles, probabilities
  powder.py        powder score
  pipeline.py      one forecast run -> site/data/*.json + archive
  verify.py        scoring and scorecard JSON
  cli.py           `python -m tahoe_snow <command>`
site/              index.html, resort.html, scorecard.html, method.html, app.js, style.css
tests/             one test file per module
reports/           snow-model report (markdown + figures), generated
```

## Task 1: Project skeleton, config, cache, physics

- `config.py`: `RESORTS` (name, lat, lon, base_m, summit_m, station id),
  `STATIONS`, `DET_MODELS`, `ENS_MODELS`. Elevations from OpenSkiMap.
- `cache.get_json(url, params, max_age_h=None) -> dict` with on-disk cache.
- `physics.wet_bulb_c(t_c, rh_pct, p_hpa) -> array` (iterative psychrometric,
  not Stull, since it must hold at 600–850 hPa),
  `physics.interp_profile(levels_hpa, heights_m, values, target_m) -> array`,
  `physics.snow_level_m(heights_m, wet_bulb_c, threshold_c=0.5) -> float`,
  `physics.kuchera_slr(tmax_k) -> array`.
- Tests: wet-bulb equals T at 100 % RH; wet-bulb at 0 °C/50 % RH/700 hPa is
  between −5 and −3 °C; snow level interpolates between two levels and returns
  the lowest crossing; Kuchera gives 12 at 271.16 K, 22 at 261.16 K, 10 at
  272.16 K.

## Task 2: Observation sources

- `snotel.daily(station, start, end) -> DataFrame[date, swe_mm, depth_cm, prec_mm, tavg_c]`
  and `snotel.hourly(...)`.
- `ghcn.daily(station, start, end) -> DataFrame[date, snow_mm, prcp_mm, tmax_c, tmin_c, wesf_mm]`,
  `ghcn.find_stations(bbox, min_elev_m, needs=("SNOW","PRCP")) -> DataFrame`.
- Station set for training: all GHCN stations with SNOW and PRCP in the Sierra
  box 36.0–40.5 N, 121.5–118.0 W at or above 1,500 m, plus all SNOTEL in the
  Tahoe box. Record the observation time convention per source.
- Tests on recorded responses: units converted; missing values become NaN;
  Tahoe City 2019-02-15 parses to 559 mm snow and 41.9 mm liquid.

## Task 3: Predictor sources

- `narr.profile(lat, lon, start, end) -> DataFrame[time, level_hpa, t_c, rh_pct, wind_ms, height_m]`
  (3-hourly, 1979 on). Time the access first; if a month costs more than about
  30 s per variable, switch to OPeNDAP with level subsetting or limit to
  Nov–Apr from 2000 on. Run the bulk pull in the background.
- `openmeteo.historical_profile(lat, lon, start, end, model="gfs_seamless")`
  with the same columns (hourly, 2021-12 on), plus surface precipitation.
- Tests: column contract; RH derived from specific humidity matches a known
  value; nulls preserved.

## Task 4: Snow-ratio dataset

- `dataset.ratio_events(obs, profiles) -> DataFrame`, one row per station-day:
  target `slr = snow_mm / liquid_mm`; predictors computed over the hours in the
  observation window, weighted toward hours when the reanalysis or model shows
  precipitation: temperature at station height and at 500, 1,000, 2,000 m
  above it; wind speed at the same heights; RH at the same heights; maximum
  temperature below 500 hPa; liquid amount; station elevation; day of year.
- Quality rules: liquid ≥ 2.5 mm; snow ≥ 25 mm; 2 ≤ SLR ≤ 40; day max wet-bulb
  at station ≤ 0.5 °C (all-snow events only, so phase is not mixed into
  ratio); drop flagged or estimated observations.
- SNOTEL events (daily SWE gain ≥ 5 mm and depth gain) are built the same way
  but kept in a separate table: they test the model at 2,400–2,700 m, and their
  known low bias from settling is reported, not hidden.
- Tests: window alignment for a morning observer; an event with rain is
  excluded; weights sum to 1.

## Task 5: Snow-ratio models and selection

- Candidates: fixed 10:1; station climatology; Kuchera; ridge regression;
  random forest; gradient boosting (`HistGradientBoostingRegressor`), each on
  the Task 4 predictors, and the two learners also with a reduced
  temperature-and-wind-only set.
- `ratio.cross_validate(events, models, by="season") -> DataFrame` with
  leave-seasons-out folds (no season in both train and test) and a second
  leave-stations-out pass to test transfer to sites never seen.
- Metrics per model: SLR mean absolute error, bias, R², and snowfall error in
  inches given observed liquid. Break out by temperature band and elevation.
- Second test on the 2021–2026 window with GFS-archive predictors in place of
  reanalysis, since forecasts come from models, not reanalysis.
- Third test against the SNOTEL table at upper-mountain elevations.
- Selection rule: the shipped model has the lowest season-held-out snowfall
  error, provided it also beats Kuchera on the GFS-driven test and on
  leave-stations-out. Fit on all data, save with `joblib`, record the feature
  list and training span in a JSON sidecar.
- `reports/snow_model.md`: the full table, figures, and what failed.
- Tests: folds never share a season; a synthetic data set where SLR is a known
  function of temperature is recovered within tolerance; the saved model
  reloads and predicts identically.

## Task 6: Rain/snow split

- Target at SNOTEL: daily snow fraction = SWE gain / precipitation gain,
  clipped to 0–1, on days with at least 5 mm precipitation.
- Candidates: air-temperature threshold; wet-bulb 0.5 °C level with a linear
  ramp of fixed depth; logistic in wet-bulb at station height (fitted).
- Choose by held-out-season error in snow water. Hourly application: each
  hour's liquid gets its own fraction from that hour's profile.
- Tests: fraction is 1 well below freezing, 0 at +5 °C wet-bulb, monotonic.

## Task 7: The snow model

- `model.snowfall(liquid_mm, profile, elevation_m) -> DataFrame[time, snow_cm, slr, snow_fraction, snow_level_m]`
  hourly: fraction from Task 6, ratio from Task 5, snow = liquid × fraction ×
  ratio / 10.
- End-to-end check, independent of the pieces: observed liquid in, snowfall
  out, against measured daily snowfall on held-out seasons at both the manual
  stations and SNOTEL, compared with 10:1, Kuchera, and Open-Meteo's 7:1.
- Tests: zero liquid gives zero snow; nulls propagate; totals are the sum of
  hours.

## Task 8: Bias correction of liquid

- `biascorrect.fit(pairs, min_wet_days=40) -> Correction` and
  `Correction.apply(model, station, lead_day, values)`; empirical quantile
  mapping on wet days, shrunk toward the pooled Tahoe mapping by sample size,
  values above the training maximum scaled by the top-quantile ratio.
- Training pairs: historical-forecast API (short lead, 2021 on) and
  previous-runs API (lead days 1–7, about 2024 on) against SNOTEL daily liquid.
- Tests: identity when forecast equals observation; a model that is 30 % dry
  is corrected to within 5 %; thin samples fall back toward the pooled map.

## Task 9: Blend, ranges, powder score

- `blend.combine(det, ens, weights) -> DataFrame` with totals, 10/50/90th
  percentiles, P(≥ 6 in), P(≥ 12 in); ensembles use the parent model's
  correction; equal weights until error history exists.
- `powder.score(day_part) -> float` 0–10 with the formula in one readable
  function and the same text rendered on `method.html`.
- Tests: percentiles ordered; probabilities in 0–1; a rain day scores 0; a
  cold, calm 12 in overnight day scores above 8.

## Task 10: Backtest and scorecard

- `verify.backtest(seasons) -> DataFrame` replays archived forecasts through
  Tasks 7–9 with corrections trained only on earlier seasons.
- Baselines: raw GFS, IFS, ICON, GEM with 10:1 and Kuchera; Open-Meteo
  snowfall; NBM where archived.
- `verify.scorecard() -> dict` pooled by lead day and per station: mean
  absolute error and bias for liquid and for snowfall.
- Apply the spec's fallback rule per lead day and record which path shipped.

## Task 11: Pipeline and site

- `pipeline.run()` fetches, corrects, converts, blends, writes
  `site/data/forecast.json`, `site/data/scorecard.json`, and an archive file
  per run; stale-data behavior per Review focus 5.
- Site pages per the spec's sketch; snow-model report linked from
  `method.html`. Weak-station and not-yet-verified labels as specified.
- Verify in a browser at desktop and phone widths.

## Task 12: Automation (after Sean's go-ahead)

- `.github/workflows/forecast.yml`: every 6 hours, run, commit data, deploy
  Pages. Not created on GitHub until Sean says so.

## Execution

Native, in this session, in task order. Tasks 2–7 (the snow model) get the
most time; the long reanalysis pull runs in the background while later tasks
are built on the 2021-on GFS archive, then the snow model is refit on the full
record.
