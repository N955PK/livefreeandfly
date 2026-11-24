# A Cascades snow model for the Seattle region: sizing and plan

Written 2026-11-23. Nothing was trained and no archive data was read for this: every size below comes from
listings and file headers (`fs.ls`, `meta.json`, each file's shape and chunk layout), two station-metadata
requests to NRCS, and tables already on this machine. No Open-Meteo API was called.

## The short version

- **Everything a Cascades fit needs is about 0.2 GB to download and 5 to 20 minutes to read**, all from the
  unmetered S3 archive and NRCS. Size is not the obstacle.
- **The first thing to fix is not a model.** The forecast reads the air column down to 850 hPa (about 1,450 m)
  and holds the lowest value constant below that. Tahoe never notices; the Cascade passes are below it. In today's
  published Seattle forecast the Summit at Snoqualmie, Alpental and Mt. Baker Ski Area show the same temperature at
  base and mid for all 519 hours, and Stevens Pass for 329 of 519. Bases are forecast too cold, so rain is called
  snow. No amount of training fixes that; three more pressure levels do.
- **Then fit in this order:** the liquid correction (cheap, low risk, turns "Uncorrected" into "Corrected"), the
  blend weights (free once the correction's test table exists), the rain/snow split (a three-number refit, the
  biggest maritime gain), and last the snow-density model, which should be checked before it is retrained because
  the Cascades have almost no hand-measured snowfall to train it on.

## Done since: the liquid correction (2026-11-23)

Sean said to fit it. `models/bias_seattle.json` is in use; the Sierra files are untouched (checksums compared).

- **What it cost.** Ten NRCS requests (about 2,240 days a station) and 381 archive files read in 3 minutes, 275 MB
  of cache. No Open-Meteo API call.
- **What the data showed.** Every model is dry against the sensors: ECMWF carried 66 % of the measured water, ICON
  and GEM 76 %, GFS 82 %. Tahoe's map applied here leaves the blend at 88 % and barely moves the error, so a local
  fit was needed.
- **Held-out test**, each of the 2024, 2025 and 2026 winters scored by a fit that never saw it, four-model average,
  ten stations:

  | | Total vs measured | Daily error (in) | 3-day error (in) | 3-day error, 2 in+ storms (in) |
  |---|---|---|---|---|
  | Raw | 72 % | 0.24 | 0.55 | 1.33 |
  | Corrected | 101 % | 0.20 | 0.40 | 0.78 |

  Corrected beat raw on every one of those measures in each of the three winters.
- **Two stations get the pooled curve.** Morse Lake (Crystal) and Pigtail Peak (White Pass), east of the crest: the
  models were half as wet as these two in 2024 and 2025 and nearly as wet in 2026, so their own curves overshot the
  held-out winter. The pooled curve beat both their own curve and raw (`calibrate.POOLED_ONLY`).
- **The three volcanoes with sensors are left uncorrected** (`Resort.corrected=False` on Mt. Rainier, Mt. Baker and
  Mt. St. Helens): the page shows their sensor and the models are used as they are at every height. This is the
  cautious half of decision 4 below; correcting their bases by height is still open.
- **Blend weights are not worth a file.** Seattle's held-out errors give 0.256 / 0.242 / 0.253 / 0.249, which is
  equal weights. The Sierra's stay in use.
- **Seattle's weights are saved anyway** (`models/weights_seattle.json`, at Sean's request, so the region's blend is
  on record as fitted there). `calibrate.save_weights` now writes such a file from the held-out table, and run on
  the Sierra's table it reproduces `weights.json` exactly. `pipeline.load_weights` reads a region's own file where
  there is one.
- **The 850 hPa floor is fixed for Seattle** (`Region.low_levels`): its forecast asks for 950, 925 and 900 hPa as
  well. A low level a model reports for only part of the forecast is left out for that model, so nothing gets
  holes. Planned calls go from 7,266 to 7,462 a day of 8,500. The Sierra and New England requests are unchanged.
  Not yet seen live: it takes effect on the collector's next Seattle pass.
- **Not done:** the rain/snow split and the density check, as planned below. The testing page's scorecard has no
  Seattle section yet. New England's mountains are below 850 hPa too and still held at it.

## 1. How the Sierra models were fitted, and what a Cascades version needs

### Liquid bias correction (`calibrate.py`, `biascorrect.py`)

- **Forecast side.** `archived_daily` reads `precipitation/chunk_*.om` from `s3://openmeteo/data/` for four
  folders: `ncep_gfs013`, `ecmwf_ifs025`, `dwd_icon`, `cmc_gem_gdps`. It takes every chunk file the folder holds
  (no winter list), reads one box per file (`TAHOE_BBOX`, `MAMMOTH_BBOX`, plus a one-cell margin), caches each
  block as `.npy` under `.cache/raw/om_precip/`, picks the grid cell nearest each station, and sums to days that
  run midnight to midnight Pacific standard time. Only November to April is kept.
- **Sensor side.** `observed_daily` reads a table of daily gains (`snotel_daily.parquet`, `mammoth_daily.parquet`)
  built by `snow/observations.py` from NRCS. Observed liquid is the larger of the gauge gain and the pillow gain.
- **Fit.** One quantile map per model and station, shrunk toward the map pooled over the region's stations
  (weight n / (n + 40) wet days), capped at the station's wettest recorded day. Lead day is always 0.
- **Output.** `models/bias.json` (Tahoe) or `models/bias_<region>.json`, plus `bias_pairs*.parquet` and
  `bias_methods*.csv` in `.cache/tables/`.
- **A Cascades version needs:** the same four folders over a box around the ten stations in
  `config.SEATTLE_STATIONS`, and those stations' daily water and gauge readings from October 2020 on.

### Rain/snow split (`snow/phase.py`, `train.fit_phase`)

- Three candidate forms (air-temperature cutoff, wet-bulb snow-level ramp, wet-bulb logistic), each a small grid.
  Target: observed snow fraction = pillow gain / liquid on SNOTEL days with at least 5 mm. Predictor: hourly
  wet-bulb at the station's height from the GFS profile, weighted by model precipitation. Parameters are chosen on
  the other seasons and scored on the held-out one.
- In use: wet-bulb logistic, centre 1.25 C, width 0.2 C (`models/snow_phase.json`), from 5,412 held-out days at
  22 Tahoe stations.
- **A Cascades version needs:** hourly GFS profiles at the stations (below) and the same SNOTEL gains.

### Snow density (`snow/dataset.py`, `ratio.py`, `train.py`)

- **Rows.** One per station-day. Hand-measured stations (GHCN: snowfall and liquid, with the observer's hour) and
  SNOTEL (liquid = pillow gain, snow = depth gain). A row trains the ratio only if it is all snow (wet-bulb never
  above 0.5 C), has at least 2.5 mm of water and 25 mm of snow, and a ratio between 2 and 40.
- **Predictors.** 19 features from the hourly GFS profile at the station's height: temperature, wind and humidity
  at 0, 500, 1,000 and 2,000 m above the site, wet-bulb, warmest layer, lapse, the day's water, elevation, season.
- **Profiles.** `ncep_gfs025` pressure-level files on S3 (temperature, humidity, two wind components, height, at
  eight levels 850 to 500 hPa) plus `ncep_gfs013` precipitation. S3 starts 2023-11-19; the two winters before that
  came from the historical-forecast API, which is metered and off limits here.
- **In use:** ridge regression on all features, fitted to **1,197 hand-measured days at 44 Sierra stations**
  (1,504 to 2,650 m), winters 2022 to 2026. The 3,031 SNOTEL rows were used for cross-checks, not the final fit.
- **A Cascades version needs:** GFS profiles over a Cascades block, SNOTEL depth and water, and whatever
  hand-measured snowfall exists (very little; see section 2).

### Blend weights (`models/weights.json`)

No code writes this file. The numbers are `blend.inverse_error_weights` applied to each model's corrected daily
error in `bias_test.csv` (the output of `calibrate.held_out_test`), averaged over the held-out 2025 and 2026
winters; recomputing that reproduces 0.268 / 0.209 / 0.284 / 0.238 exactly. A Cascades version needs nothing
beyond the liquid correction's own test table.

## 2. Sizing

### What the archive holds (precipitation, listed 2026-11-23)

| Folder | Files | Folder size | Covers | Grid | Step |
|---|---|---|---|---|---|
| `ncep_gfs013` | 97 | 41.3 GB | 2021-03-12 to now, **missing 2022-12-14 to 2023-05-23** | 1536 x 3072 | 1 h |
| `ecmwf_ifs025` | 81 | 3.1 GB | 2024-01-25 to now | 721 x 1440 | 3 h |
| `dwd_icon` | 122 | 21.5 GB | 2023-05-25 to now | 1441 x 2879 | 1 h |
| `cmc_gem_gdps` | 81 | 7.4 GB | 2023-05-20 to **2026-06-07, then stops** | 1201 x 2400 | 3 h |

So all four models overlap on three winters: 2024 (ECMWF from late January), 2025 and 2026. That is the same
window Tahoe and Mammoth were fitted on. The GEM folder was last written on 2026-05-26; its correction cannot be
refreshed with this winter.

### Reading a box, not files

Each file is stored in strips of one grid row by 6 to 29 columns by the whole time span, and the reader fetches
only the strips a box touches (opening a file costs three tiny requests: I logged them). Bytes scale with the
box's area, and are a few ten-thousandths of the folder.

| Box | Size | Files | Strips read per file (GFS / ECMWF / ICON / GEM) | Download | Cache on disk |
|---|---|---|---|---|---|
| Tahoe | 145 x 104 km | 381 | 42 / 8 / 28 / 12 | ~5 MB | 63 MB (61 MB measured) |
| Eastern Sierra | 145 x 114 km | 381 | 42 / 8 / 26 / 22 | ~6 MB | 66 MB |
| **Seattle** (46.0 to 49.0 N, 123.6 to 120.3 W) | 334 x 248 km | 381 | 168 / 30 / 81 / 46 | **~20 MB, at most ~60** | **287 MB** |

"Download" is each file's size times the share of its strips the box touches; precipitation compresses worse where
it is wet, so I give three times that as the ceiling. The cache figure is exact (points x steps x 4 bytes). The
Seattle box is 5.3 times Tahoe's area and costs about four times as much, which is still nothing. A box this wide
is only read because the ten stations are spread over it; only ten cells are used.

### Upper-air profiles (rain/snow split and density)

`ncep_gfs025` has every level from 1000 to 10 hPa, 56 files per field per level, 2023-11-19 to now. Five fields are
read per level.

| Block | Levels | Files | In the archive | Download | Cache on disk |
|---|---|---|---|---|---|
| Sierra, as trained (17 x 15 nodes) | 8 | 2,240 | 486 GB | ~143 MB | 1.10 GB (1.1 GB measured) |
| Cascades (13 x 15 nodes) | 8 | 2,240 | 486 GB | ~109 MB | 0.84 GB |
| **Cascades with 950, 925 and 900 hPa added** | 11 | 3,080 | 684 GB | **~154 MB** | **1.16 GB** |

### Sensors (NRCS answered in 2.4 s and 0.9 s today; it was not slow)

Every one of the ten Seattle stations has had water (pillow and gauge) and depth since 2006 or earlier, so each
covers the whole archive window. The sensors are not the limit; the archive's three winters are.

| Station | Elevation | Water since | Depth since |
|---|---|---|---|
| Morse Lake | 5,400 ft | 1978 | 2005 |
| Stevens Pass | 3,940 ft | 1980 | 2002 |
| Olallie Meadows | 4,010 ft | 1982 | 2003 |
| Wells Creek | 4,040 ft | 1995 | 1996 |
| Pigtail Peak | 5,800 ft | 1981 | 1996 |
| Grouse Camp | 5,390 ft | 1982 | 2003 |
| Waterhole | 5,010 ft | 1999 | 1999 |
| Paradise | 5,150 ft | 1980 | 2006 |
| Marten Ridge | 3,520 ft | 2006 | 2006 |
| Swift Creek | 4,440 ft | 2002 | 2002 |

There are 64 active SNOTEL stations inside the Seattle box (1,680 to 6,490 ft, all but one older than 2021), should
the split or the density model want more than the ten that are paired with mountains.

Hand-measured snowfall is the gap. From the GHCN inventory already cached here: stations in the box reporting
snowfall and liquid into 2023 or later number 14 above 600 m, **2 above 900 m** (Rainier Paradise Ranger Station
at 1,650 m and Holden Village at 981 m) and 1 above 1,200 m. The Sierra had 44.

### Training rows against the Sierra's

| Model | Sierra, measured | Cascades, estimated (rows are not pulled yet) |
|---|---|---|
| Liquid correction | 17,820 station-days at 22 stations; 52,206 model-days; about 290 wet days per station for GFS | ~8,100 station-days at 10 stations; ~23,700 model-days; more wet days per station, since it rains or snows on more winter days |
| Rain/snow split | 5,412 scored days, 22 stations, 5.5 winters; 1,221 of them mixed | ~3,000 days at 10 stations over 3 winters; ~18,000 with all 64 stations; a much larger mixed share |
| Density, hand-measured | 1,197 days at 44 stations | a few hundred at best, most of them from Paradise alone |
| Density, SNOTEL depth gain | 3,031 days at 22 stations (cross-check only) | ~1,000 at 10 stations; ~6,000 at 64 |

### Total

| Step | Requests | Download | Disk | Time |
|---|---|---|---|---|
| Liquid correction: four models' precipitation | 381 files (~19,000 small ranges at worst) | 20 to 60 MB | 287 MB | ~4 min on its 12 threads |
| Sensors: ten stations' daily record from 2020 | 10 | ~10 MB | ~10 MB | under 5 min if NRCS behaves |
| Profiles: GFS levels, 11 levels | 3,080 files (~89,000 ranges at worst) | ~154 MB | 1.16 GB | ~14 min on its 16 threads |
| **All of it** | **~3,470 files** | **~0.2 GB** | **~1.5 GB** | **5 to 20 min** |

The time is the soft number: it assumes 0.15 s a request (what three header requests cost) and two requests per
grid row. The code's own note says a block costs "a fraction of a second per file", which would put the whole thing
nearer five minutes. Either way every block is cached, so a stalled run resumes.

## 3. What to fit, in what order

### First: the 850 hPa floor (not a model, but everything else depends on it)

`config.PRESSURE_LEVELS` is 850 to 500 hPa and `physics.interp_profile` holds the ends constant. Five of the ten
Seattle stations (Stevens Pass, Olallie Meadows, Wells Creek, Marten Ridge, Swift Creek) and all of Snoqualmie,
most of Alpental and Mt. Baker Ski Area, and the bases of Stevens, Crystal, White Pass and the volcanoes sit below
850 hPa. Their temperature, wet-bulb and humidity are the 850 hPa values. At Snoqualmie's base that is about 650 m
too high, roughly 4 C too cold, in a region where the rain line is the whole question.

Fix: give Seattle 950, 925 and 900 hPa as well (950 hPa is about 540 m, below Glacier Peak's 630 m trailhead). By
the service's rule that is 12 more variables for four models over 22 days, **7.5 more calls a mountain a run, 196 a
day for Seattle**, taking the plan from 7,266 to about 7,460 of 8,500. It must be per region so Tahoe's request,
and so Tahoe's numbers, do not change. Train with the same levels the live forecast uses, or the fit learns the
clamped column. (New England's mountains are lower still and have the same floor; that is its own job.)

### (a) Liquid correction: do it first

- **Gain.** At Tahoe the raw four-model average carried 88 % of the measured water and the correction brought it
  to 102 %, cutting the error on 2 in+ storms from 0.90 to 0.59 in. The Cascade crest is narrower than the models'
  grid, so the raw error should be at least as large, with the east side (Mission Ridge) likely too wet. It is also
  what the page's tag reports.
- **Data.** 20 to 60 MB and ten sensor requests.
- **Risk.** Low. A capped quantile map, shrunk toward the region's pool, in its own file. Three winters is thin for
  the wettest days, which is what the cap is for.
- **Validation.** `calibrate.held_out_test` and `storm_test` as they are, holding out 2024, 2025 and 2026 in turn
  (Mammoth's test). Ship it only if the corrected blend beats raw on 3-day error and on 2 in+ storms in each held-out
  winter and brings the total nearer 100 %; look at each station, and drop any the correction makes worse. Also
  score Tahoe's map on Seattle's stations as a baseline, as was done for Mammoth, to show a local fit is needed.

### (c) Blend weights: free, straight after (a)

- **Gain.** Small. The Sierra weights only range from 0.21 to 0.28, and the day's total comes from the median of
  the models anyway (`blend.robust_mean`); weights mostly shape the hours.
- **Data.** None beyond (a): the per-model rows of the held-out table.
- **Risk.** Low, if the weights are computed from held-out error only, as the Sierra's were.
- **Validation.** Score the weighted blend against the equal-weight blend on the held-out winters; keep equal
  weights unless it wins in both 2025 and 2026.

### (b) Rain/snow split: refit for the region, after the floor is fixed

- **Gain.** The largest for maritime snow. Tahoe's centre of 1.25 C wet-bulb was chosen where 23 % of days are
  mixed; at the passes most storms are near the line. Published work puts the rain/snow threshold lower in maritime
  ranges than inland, so the Sierra value probably calls too much snow.
- **Data.** The profiles (~154 MB) and the same sensor table.
- **Risk.** Moderate. Rain soaking into a deep snowpack raises the pillow, so the "observed" snow fraction is
  overstated on some rain days; days where the pillow gains and the depth falls should be dropped or flagged. With
  three winters, hold a winter out rather than trust the in-sample grid.
- **Validation.** `train.fit_phase` unchanged: parameters chosen on the other winters, scored on the held-out one,
  reported as water wrongly called rain or snow per wet day and on mixed days, against Tahoe's parameters applied
  as they are. Adopt `snow_phase_seattle.json` only if it beats Tahoe's on held-out mixed days.

### (b) Snow density: check first, retrain only if the check says so

- **Options.** (1) Cascades rows only: not enough hand-measured data, and SNOTEL depth gain reads low because the
  new snow settles within the day. (2) Sierra and Cascades pooled, region as a feature: workable, and the Sierra
  rows keep the cold end honest. (3) Keep the Sierra model and measure it.
- **Recommendation.** Do (3) first. It costs nothing more once the profiles are cached: build Cascade event rows
  and run `ratio.train_on_apply_to(sierra, cascades)` and `train.end_to_end` on them. The model already takes
  temperature, wet-bulb and wind, which carry most of the "wetter and denser" signal; what it has never seen is
  sites below 1,500 m, and elevation is one of its inputs, so it is extrapolating at every pass. If the check shows
  a bias (I expect too fluffy at the passes), go to (2), saved as its own file for Seattle only.
- **Gain.** Unknown until checked; at Tahoe the trained ratio beat Kuchera by 0.36 in a day (1.66 against 2.02).
- **Risk.** The highest of the four: thin truth, a sensor target with a known low bias, and a model that could get
  worse in exactly the storms people care about. A resort-run snow stake record (the avalanche center's or the
  resorts') would be far better truth than SNOTEL depth; whether one can be used is a question for Sean.
- **Validation.** Leave-one-winter-out (`ratio.cross_validate(by="season")`) on Cascade rows, plus leave-one-
  station-out since there are few stations; score in inches of snow given measured water, split by temperature band
  (`train.band_table`), with Paradise's hand-measured days held entirely out as the final judge.

### What must not change for Tahoe and the Eastern Sierra

`models/bias.json`, `bias_mammoth.json`, `snow_ratio.joblib`, `snow_ratio.json`, `snow_phase.json` and
`weights.json` stay byte-for-byte (check `git diff --stat models/` is empty apart from new `*_seattle*` files).
`PRESSURE_LEVELS` keeps its eight levels for those regions. No Sierra station joins a Cascades pool and no Cascades
row is added to a file the Sierra regions load. A test should forecast one Tahoe and one Mammoth mountain from a
saved response before and after and compare the numbers exactly.

## 4. Code changes

- **`config.py`.** `SEATTLE_BBOX = (46.0, 49.0, -123.6, -120.3)`; a per-region list of pressure levels on `Region`
  (default the current eight; Seattle adds 950, 925, 900).
- **`calibrate.REGIONS`.** Add `"seattle": (SEATTLE_STATIONS, SEATTLE_BBOX, "seattle_daily")`. Nothing else in
  `calibrate.py` needs to change; the phantom filter only runs for CDEC regions.
- **`snow/observations.py`.** `pull_mammoth` already handles SNOTEL stations; turn it into a `pull_region(stations,
  table, start)` and call it for Seattle.
- **`pipeline.load_corrections`.** Already per region: it will pick up `bias_seattle.json` with no change, and
  `write_index` will flip Seattle's mountains to Corrected by itself. One stray: `run` writes
  `"bias_corrected": "tahoe" in corrections` into every region's file; it should be the region's own.
- **`pipeline.load_snow_model`.** Take a region: use `snow_phase_<region>.json` and `snow_ratio_<region>.joblib`
  where they exist, else the current files. `run` already loads once per region. The page's sentence ("trained on
  ... hand-measured Sierra snow days") should come from the file actually used.
- **`pipeline.load_weights`.** Same pattern: `weights_<region>.json`, else `weights.json`.
- **`openmeteo.level_variables` and `resort_forecast`.** Pass the region's levels. `features.levels_in` already
  works from whatever levels the frame holds. `usage.CALLS_PER_RESORT_RUN` becomes per region.
- **`sources/omfiles_s3.py` and `snow/dataset.py`.** The block (`LAT0..LON1`), `sierra_profiles`, `STATIONS` and
  `SIERRA_BBOX` are hard-wired; they need a region argument. `dataset.Profiles` must skip the "early cells" path
  for Seattle, since that path calls the metered API.

### The volcanoes

In the Sierra code `weak_match` is a label and nothing more: it makes the page say "Low sensor". The station's
correction is still applied in full, and because one corrected liquid series feeds base, mid and summit
(`model_snow`), it is applied at every height. The furthest any Sierra mountain reaches above its sensor is about
930 m (Matterhorn Peak over Slide Canyon). Rainier's summit is 2,820 m above Paradise, Mt. Baker's 2,210 m above
Marten Ridge, Mt. St. Helens' 1,200 m above Swift Creek, and precipitation on a big volcano stops rising well below
the top. A map learned at a pass-level sensor says nothing about 14,410 ft.

Recommendation: for the Seattle volcanoes apply the correction by height. Full within 300 m of the sensor (the
pairing rule the region guide already uses), fading to none 1,000 m above it. That corrects Rainier's and Baker's
bases, most of St. Helens' lower half, and leaves every upper mountain as the models have it. It needs
`corrected_liquid` to be called per elevation, switched on by a field on the mountain so that Alpine Meadows,
Northstar and Matterhorn Peak keep their numbers. Glacier Peak and Mt. Adams have no sensor and stay uncorrected,
as the code already does. The same honesty applies to density: no sensor exists high on a volcano, so nothing fitted
here can be validated up there, and the forecast for the upper mountain remains the models plus Sierra physics.

## 5. Decisions for Sean

1. **Add 950, 925 and 900 hPa to Seattle's live forecast?** About 196 more calls a day (7,266 to ~7,460 of 8,500).
   I recommend yes, before anything is fitted.
2. **Go-ahead to pull the data:** ~0.2 GB from S3 (unmetered) and ten NRCS requests. Nothing metered.
3. **Ten stations or all 64** for the rain/snow split and the density check? The correction uses the ten paired
   ones either way. I recommend all 64 for the split, since it is a regional rule, not a per-station one.
4. **The volcano rule:** correct by height as above, or leave all five uncorrected until there is a reason not to.
5. **Density truth:** is there a resort or avalanche-center snow-stake record that may be used? Without one the
   density model gets a check and, at most, a pooled refit judged on Paradise.
