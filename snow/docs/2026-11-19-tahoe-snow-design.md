# Tahoe snow forecast: design

Date: 2026-11-19. Status: draft for Sean's approval.

## Intent

A free snow forecast for Tahoe ski resorts that is measurably more accurate
than the free baselines OpenSnow benchmarks itself against, and that shows its
own scorecard. Sean asked for "OpenSnow but better, and free", and picked the
"verified, Tahoe first" approach.

Why it can work: OpenSnow's inputs are all public model data and public station
observations. Their published verification covers temperature, wind, and liquid
precipitation, not snowfall or snow ratio. The literature says per-site bias
correction and a trained snow-to-liquid ratio are the two largest wins, and
both are doable with free data.

## Goals

1. Hourly and daily snowfall forecasts at base, mid, and summit for each
   covered resort, out to 10 days.
2. Liquid precipitation bias-corrected per site against station history.
3. Snow-to-liquid ratio (SLR) and snow level computed by us, not taken from a
   flat ratio.
4. Honest uncertainty: a 10th–90th percentile range on every total, and
   probabilities only (chance of 6 in or more, 12 in or more) for days 6–10.
5. A transparent powder score with the formula printed on the page.
6. A public scorecard, updated daily, comparing our forecasts with the
   baselines at the stations.
7. Zero running cost, no API keys.

## Non-goals

- Resorts outside the Tahoe area (the pipeline should not block adding them).
- Written forecaster discussions, maps, webcams, avalanche forecasts, alerts,
  mobile apps, accounts.
- Days 11–15.
- Ads or any monetization (Open-Meteo's free tier is non-commercial).

## Anti-goals

- Claiming "better" anywhere the scorecard does not show it.
- Using resort-reported snowfall (no free feed; scraping breaks their terms).
- A snow-ratio or bias model that ships without beating the simple baseline on
  held-out data.

## Constraints

- Open-Meteo free tier: 10,000 calls/day, 5,000/hour, 600/minute per IP;
  CC BY 4.0, attribution required.
- GitHub Actions cron runs can be 5–30 minutes late, and schedules in a public
  repo are disabled after 60 days without repo activity (the daily data commit
  counts as activity).
- Open-Meteo lists HRRR as discontinued on 2026-11-30, with RRFS replacing it;
  an RRFS test call returned empty. v1 must not depend on a named hi-res model.
- Forecast archive depth, checked today at Palisades: GFS from at least
  2021-12, ICON and GEM from 2022-12, ECMWF IFS null through 2023-12 but
  present by 2025-01. Lead-time archives (previous-runs API) returned data for
  2025-01. NBM was null in all three archive dates tried.

## Approaches considered

- **A. Quick version.** Open-Meteo models at three elevations plus a better
  snow ratio and one page. A day or two of work, but with no bias correction it
  is only more transparent, not more accurate.
- **B. Verified, Tahoe first (picked by Sean).** A, plus per-site bias
  correction against stations, a trained SLR, wet-bulb snow level,
  probabilities, a powder score, and a scorecard. It is the smallest version
  that can actually test "better", and bias correction needs a nearby station,
  which Tahoe has.
- **C. Full clone.** Raw model grids from NOAA and ECMWF, terrain downscaling
  everywhere, every resort. Months of work; B can grow into it.

## Coverage

Resorts and their paired SNOTEL station (all stations confirmed active today
via the NRCS API; pairings are my call from the map and need a sanity check in
the build):

| Resort | Station (id, elevation) |
|---|---|
| Palisades Tahoe | Palisades Tahoe (784, 8,010 ft) |
| Alpine Meadows | Ward Creek #3 (848, 6,750 ft) |
| Homewood | Ward Creek #3 (848) |
| Sugar Bowl, Boreal | CSS Lab (428, 6,890 ft) |
| Northstar | Truckee #2 (834, 6,500 ft): weak match, lower and drier |
| Mt. Rose | Mt Rose Ski Area (652, 8,810 ft) |
| Heavenly | Heavenly Valley (518, 8,540 ft) |
| Sierra-at-Tahoe | Echo Peak (463, 7,650 ft) |
| Kirkwood | Carson Pass (1067, 8,360 ft) |

Resort coordinates and base/summit elevations come from OpenSkiMap. Mid is the
midpoint.

## How it works

Python 3.11, numpy/pandas/scipy/scikit-learn, no web framework. One command
runs the whole pipeline; a GitHub Actions schedule runs it every 6 hours and
commits the output.

1. **Fetch.** Open-Meteo forecast API for the deterministic models (GFS
   seamless, ECMWF IFS, ICON, GEM, NBM, AIFS) and the ensemble API (GEFS,
   IFS ENS, ICON EPS, GEM), at each resort's three elevations and at each
   station's own elevation. Variables: hourly precipitation, temperature,
   humidity, and wind at the surface and at pressure levels, plus freezing
   level where the model has it. Stations: SNOTEL hourly snow depth, snow water
   equivalent (SWE), accumulated precipitation, and temperature; CDEC as a
   second source where a sensor is closer.
2. **Bias-correct liquid.** For each station, model, and lead-day bucket, map
   forecast 24 h precipitation onto the observed distribution (empirical
   quantile mapping, wet days only). Observed liquid is SNOTEL daily SWE gain,
   falling back to accumulated-precipitation gain on days with rain. Where the
   sample is thin (few wet days at that lead), fall back to a single bias ratio
   shrunk toward 1. The correction learned at a station is applied to its
   paired resort at all three elevations. That transfer is an assumption; the
   scorecard only verifies it at the station.
3. **Snow level and phase.** Height of the 0.5 °C wet-bulb temperature from
   the pressure-level profile. Above it, all snow; SLR ramps linearly to zero
   through a transition zone below it (start at 300 m; tune on backtest).
4. **Snow ratio.** Candidates, all scored on held-out seasons:
   flat 10:1, Kuchera, and a regression trained on Tahoe-station events
   (predictors per the Utah work: temperature and wind speed at levels above
   the site, humidity, and liquid amount; reanalysis predictors from
   Open-Meteo's archive API). Training events are days with SWE gain of at
   least 5 mm, depth gain, and cold temperatures, since SNOTEL depth is noisy
   and settles. The trained model ships only if it beats Kuchera on held-out
   seasons; otherwise Kuchera ships and the page says so.
5. **Blend and spread.** Deterministic total = weighted mean of the
   bias-corrected models, weights from each model's recent error at that lead
   (equal weights until there is enough history). Ensemble members get the same
   correction, SLR, and snow level, giving the 10th/50th/90th percentiles and
   the chance of at least 6 in and 12 in. Days 1–5 show a total with its range;
   days 6–10 show probabilities only.
6. **Powder score.** A 0–10 number per day-part from: new snow amount, SLR
   (best around 12–20), whether density decreases upward through the storm,
   ridge-top wind during and 12 h after snowfall, snow level relative to base
   and summit, rain-on-snow, and overnight timing. Formula and weights are
   printed on the site. Weights are a starting judgment, not fitted.
7. **Verify.** Every run's forecast is archived. A daily job scores past
   forecasts at the stations: liquid against SWE gain, snowfall against depth
   gain (flagged as the noisier measure). Metrics: mean absolute error and bias
   ratio by lead day, plus reliability of the 6 in and 12 in probabilities.
   Baselines: raw GFS and IFS with 10:1 and Kuchera, Open-Meteo's own snowfall,
   NBM, and the NWS gridpoint forecast (the last two forward-only if their
   archives are empty).

## Backtest before launch

Before the site goes up, replay past seasons from the forecast archive with a
train/held-out split by season, so the scorecard starts with real numbers and
steps 2 and 4 are chosen on evidence. Lead-dependent correction can only be
trained from about 2024 on; before that, the archive is short-lead only.

**Success test:** on held-out data at the stations, the blended, corrected
24 h liquid forecast has lower mean absolute error than each raw model and NBM
(where NBM archive exists), and our snowfall beats the same liquid with 10:1
and with Kuchera. Whatever the result, it goes on the scorecard as is.

## The site

Static HTML and JavaScript, built by the pipeline, served by GitHub Pages.

```
Tahoe snow          updated Thu 6:10 am            [scorecard] [how it works]

Resort            Next 24 h     72 h        Days 4–5    Days 6–10      Powder
Palisades   top   7 in (4–11)   19 (11–28)  3 (0–9)     40 % ≥ 6 in    8.1 Fri am
            base  3 in (1–6)    9 (4–15)    1 (0–4)     snow level 6,400 ft
Kirkwood    top   9 in (5–13)   24 (14–33)  ...
...
```

Click a resort for the hourly view: snowfall and snow level by elevation, snow
ratio, ridge wind, each model's line with the blend on top, and that resort's
station scorecard.

## Sean's decisions

- Approach B, Tahoe first.
- Free, no cost.

## My calls (correct any of these)

- The resort list and station pairings above.
- 10-day horizon, probabilities only past day 5.
- Open-Meteo as the only forecast source in v1; direct NOAA grids (HRRR/RRFS,
  NBM percentiles) are a later addition if the scorecard shows short-range
  skill is the gap.
- Python, static site, GitHub Actions + Pages. A public repo on Sean's personal
  GitHub account is needed for free Actions and Pages; nothing gets pushed
  there without his go-ahead. Everything runs locally first.
- Project lives at ``livefreeandfly/snow` in Sean's personal site repo, served at livefreeandfly.org/snow/.
- No direct comparison with OpenSnow: their forecasts are paywalled and we will
  not archive them.

- **Liquid is the same at base, mid, and summit in v1.** Open-Meteo's
  elevation setting changes temperature, not precipitation, and there is one
  station per resort to correct against. Base-to-summit differences come only
  from snow level and snow ratio, and the site says so. A climatological
  elevation gradient (PRISM ratios) is a later addition; it would have nothing
  to verify against.
- **Ensembles borrow their parent model's correction** (GEFS from GFS, IFS ENS
  from IFS, ICON EPS from ICON, GEM ensemble from GEM). The ranges and the 6 in
  and 12 in chances are verified going forward only and labeled "not yet
  verified" until the scorecard has a season of them. If an ensemble archive
  turns out to exist, backtest them too.
- **The success test is pooled across stations, per lead day.** If the
  corrected blend loses to the raw blend at a lead day, the raw blend ships at
  that lead. Per-station results are shown on the scorecard but do not switch
  anything; with about two seasons of lead-time archive they are too noisy.
- **Station corrections are shrunk toward a Tahoe-wide pooled correction**,
  more strongly where a station's sample is thin. Homewood uses Ward Creek #3.
  Northstar and Alpine Meadows (station well below the mountain) carry a
  "weak station match" label on the site.

## Left to the builder

- Exact quantile-mapping sample thresholds and the shrinkage form.
- Regression family for the snow ratio (linear versus random forest), chosen on
  held-out error.
- Transition-zone depth and blend-weight window.
- Storage layout for archived runs and how much history the repo carries.
- Page styling.

## Added later: regions, backcountry, and avalanche danger

Sean asked for these on 2026-11-19, after the design above; they replace the
"outside Tahoe" and "avalanche forecasts" non-goals.

- Every location has a region (Tahoe or Mammoth), a kind (resort or
  backcountry), and a pass group. For a backcountry peak the summit is the
  peak and the base is the usual winter trailhead; both were read from the
  Terrain Tiles elevation model.
- Mammoth's water is corrected with Mammoth's own sensors (see the next section); the Tahoe map is not used
  there.
- The snow-ratio model was trained on stations up to 2,685 m; Mammoth's summit
  (3,369 m) is further above that than any Tahoe summit.
- The page reads each avalanche center's rating and forecast from avalanche.org
  in the browser. It is a pointer to the center's forecast, never a substitute.
- Eighteen locations use roughly 6,800 of Open-Meteo's 10,000 daily calls.

## Added later: Mammoth's own water correction

Sean asked on 2026-11-19 for the Mammoth forecast to use Mammoth data. What the data showed, and what is now in
use:

- Sensors. The area has one SNOTEL site (Virginia Lakes Ridge) and a set of California Data Exchange Center
  (CDEC) snow pillows; Mammoth Pass sits 2 km south of Mammoth's summit. NRCS mirrors only a slice of the CDEC
  record, so there is a CDEC reader. CDEC dates a daily value by the midnight that starts the day (checked
  against its hourly readings and against the models: the correlation peaks at zero lag).
- Water record. The CDEC precipitation gauges do not track their pillows (correlation 0.1 to 0.3, half the
  total), so the pillow is the record. Raw pillow readings jitter, and adding every daily rise overstates a
  week's water by about 20 %; a three-day median plus a 5 mm dead band holds that within a few percent. A
  station-day with 25 mm or more that no model had, that day or the days beside it, is dropped as a sensor
  step (10 of 6,560).
- The Tahoe map was wrong for Mammoth. Applied to these stations on held-out winters (2024 to 2026) it was
  worse than no correction: 3-day error 0.52 in against 0.45, and 13 % too wet at Mammoth Pass.
- In use: a correction fitted to ten stations around Mammoth, kept in its own file (`models/bias_mammoth.json`)
  so the Tahoe stations and the Mammoth stations are pooled only among themselves; Tahoe's file is unchanged.
  Over those stations it cuts daily and 3-day error by about 7 % against the raw four-model average.
- Mammoth Mountain and Sherwin Ridge use Mammoth Pass's map. At Mammoth Pass alone the blend is a tie with
  raw (daily 0.20 against 0.21 in, 3-day 0.42 against 0.41), because the models' errors there offset: GFS
  runs 32 % wet, GEM 30 % dry. The map is used anyway because it makes each model right on its own, so the
  blend does not depend on that offset when a model is missing.
- June Mountain and Carson Peak have no working sensor nearby (Gem Pass and Agnew Pass stopped reporting)
  and are left uncorrected. Gem Pass's 2022 and 2023 record says a map borrowed from Mammoth Pass or pooled
  over the area would make them worse (the models run dry there, and those maps dry them further).
- A place with no station now gets no correction at all, where it used to get the pooled map.
- Mammoth Pass's depth gauge is unreliable, so the page shows its water alone.
- Not done: the snow-ratio model is unchanged, and the blend weights are still the Tahoe ones.
