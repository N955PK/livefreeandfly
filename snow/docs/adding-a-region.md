# Adding a region to Turbo Snow

Sean names a region ("add the Wasatch"); this guide is everything that has to happen for it to be finished, in the
order to do it. Do all of it in one go. Nothing here is optional unless it says so, and the checklist below is what
"done" means: before reporting back, go down it and say for each line whether it is done, could not be done (and
why), or does not apply.

Read the **Global Constraints** of `2026-11-22-regions-plan.md` first; they all apply. Throughout, `<region>` is the
key: lower case, no spaces (`saltlake`). To add mountains to a region that exists, do the lines marked (M) only.

## The checklist

**Before starting**
- [ ] The mountains are chosen: every resort in the area on any pass, and the backcountry spots people ski there
      (volcano summits, passes, the classic lines). Ask Sean only if the area's edges are unclear.
- [ ] The call budget fits (step 0), with close neighbours sharing weather. (M)

**The forecast (first push)**
- [ ] Each mountain's point, base, summit and pass are looked up, not remembered, and the source is in the comment
      above its entry (1a). (M)
- [ ] Mountains within about 8 km of another share its weather (`weather_from`); up to about 16 km where the
      budget needs it and no crest runs between them (1a). (M)
- [ ] Snow sensors are found and paired, or the region is said to have none (1b). (M)
- [ ] `Region` has its time zone, sensor clock offset, build hours on its own clock, avalanche centers, and low
      pressure levels if any base is under about 1,450 m (1c).
- [ ] The region's own models are fitted where it has sensors: water correction, blend weights, rain-or-snow
      curve, and the snow-ratio model checked and refitted only if that beats the Sierra's (1e). Each is saved as
      the region's own file even where it barely differs.
- [ ] Tests updated and passing; pushed; collector restarted; the region's first forecast is published with every
      mountain in it (1d). (M)

**The page (second push)**
- [ ] Terrain, with a water mask where lakes or sea sit above the floor (2a).
- [ ] Road lines (2b). If Overpass is down, ship without and say so.
- [ ] Terrain, water mask and roads are in `SHELL` in `sw.js` (2b).
- [ ] The region's entry in `REGIONS`, with its opening view tuned so every mountain fits a phone (2c).
- [ ] Sub-area pills (`areas`) if the region has more than about ten mountains or spans more than one range or
      state (2c). (M: add the mountain to its area's list.)
- [ ] Summit marker positions (`PEAK_AT`) for backcountry peaks whose forecast point is not the summit (2c). (M)
- [ ] Avalanche: the centers' states are in `AVY_AREA` under the region's group, the group is in `AVY_AREAS`, and
      the small locator map has a frame for the region (`LOCATORS`) in the California style, with water where
      there is some and each zone's prominent mountain named (2c).
- [ ] Short names (`SHORT`, and the region's `short`) where a name is long for a table row (2c). (M)
- [ ] Lift status, trail counts and the resort's snow report for every resort that publishes them (step 3). (M)
- [ ] The resort's reported base depth feeds the map where the region has no sensors (`STAKES`) (step 3). (M)
- [ ] "How the forecast is made" has the region's paragraph, "How it is tested" has its results under each topic,
      and the Status paragraph says which resorts' lifts are read and which cannot be (2f).
- [ ] The scorecard has the region's sections (`verify.py`) if anything was fitted (2f).
- [ ] The page's description (`og:description`) names the region (2f).
- [ ] Checked in the preview, light and dark, at phone size (2d); pushed.

**After**
- [ ] The first real build is confirmed, and the next day's calls are under the limit (2e).
- [ ] Sean gets the short report at the end of this guide.

## 0. Check it fits

Each weather pull costs 51.9 Open-Meteo calls a run (more where the region reads extra low pressure levels). A
region is built at fixed hours on its own clock (`Region.at`; `every_h` is 24 over their number): the western
regions three times a day (5 am, 1 pm, 9 pm), New England twice (4 am, 4 pm). Sean set these; do not change a
region's hours or add builds without asking. A new western region takes the same three hours on its own clock.

A mountain that takes a neighbour's weather (`Resort.weather_from`) makes no pull and costs nothing, so count
pulls, not mountains. The day's ceiling is 9,900 (`usage.PLAN_LIMIT`; the service allows 10,000). The tests enforce it; do the sum first:

```python
from tahoe_snow import usage; print(usage.planned())   # after adding the region, before pushing
```

Adding mountains makes the collector rebuild that region straight away, outside its hours, which costs one extra
run that day. Check the last day's use in `archive/usage.json` on the data branch first, and if the day is already
near 10,000 (the service's hard limit), wait for the region's next scheduled build instead of restarting.

A region whose mountains reach below about 1,450 m needs pressure levels under 850 hPa, or every height below that
is given the 850 hPa temperature and rain is called snow. Give its `Region` `low_levels=(950, 925, 900)` as Seattle
has, or New England's `(1000, 975, 950, 925, 900)` (900 hPa is near 990 m, 925 near 760 m, 950 near 540 m, 975 near
320 m, 1000 near 110 m; take only the ones the lowest base needs). Each extra level costs 2.51 calls a mountain a
run, and `usage.planned()` counts it: with both regions the plan is 7,838 calls a day of 8,500.

One region is built in one collector pass. Eight pulls take about a minute and a half; New England's sixteen are
the most a region has held. A much bigger area is two regions.

## 1. First push: the forecast

### 1a. Pick the mountains and get their numbers

For each mountain you need: a key (lower case, no spaces, unique across all regions), its name, latitude and
longitude **at mid-mountain**, base and summit elevation in metres, and its pass (`Ikon`, `Epic`,
`Mountain Collective`, `Indy`, `Independent`, or `Backcountry`).

- The point: the midpoint of the main lift from the base in OpenStreetMap (the main OSM API's `map?bbox=` works
  when Overpass is at capacity), checked against the USGS elevation service
  (`https://epqs.nationalmap.gov/v1/json?x=LON&y=LAT&units=Feet&wkid=4326`): the height there sits between base
  and summit.
- Elevations: the resort's own published base and summit of lift-served skiing, or the Indy Pass page's. Where a
  published figure does not match the ground (a summit higher than the peak, a base below the lowest lift), use the
  height at the lift's end and say so in the comment. Feet go through `_ft()`.
- The pass for the coming season, confirmed from the pass's own list. A resort that only gives a couple of bonus
  days on a pass is `Independent`.
- Sharing weather: list every pair of mountains in the region by distance. Under about 8 km, the further-out or
  smaller one takes `weather_from="<neighbour>"`; the base of a group is the bigger, better-known mountain. Between
  8 and 16 km share only when the budget needs it and both sit on the same side of the range. Never share across a
  crest, or between a volcano's summit and a resort on its flank. A mountain that shares is still read at its own
  heights. Add each pair to `SHARED` in `tests/test_shared_weather.py`.
- Backcountry spots: summit is the peak, base is the usual winter trailhead; `kind="backcountry"`,
  pass `"Backcountry"`.
- Check every point against the terrain: after step 2a, the heightmap's height at the mountain's coordinates should
  sit between its base and summit. A point that lands in a valley or on the wrong ridge shows up there.

Do not take coordinates or elevations from memory. Look each one up and say in the commit where they came from, as
the comment above `RESORTS` does.

### 1b. Find the snow sensors

Only Washington, Oregon, Idaho, Utah, Wyoming, Montana, Colorado, Nevada, California and Alaska have SNOTEL. New
England has none: give those mountains `station=None` and skip to 1c.

- List a state's stations from the NRCS service the code already uses (no key):
  `https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=*:UT:SNTL&activeOnly=true`
  Each has a triplet (`766:UT:SNTL`), name, latitude, longitude and elevation in feet.
- Pair each mountain with the nearest station that is within about 10 km **and** within about 300 m of the
  mountain's mid elevation. Within 10 km but lower than that: pair it and set `weak_match=True`. Nothing within
  10 km: `station=None`. The page then tags the mountain Corrected, Low sensor or Uncorrected by itself.
- Add each station you use to a new dict in `config.py` beside `MAMMOTH_STATIONS`, and merge it into
  `ALL_STATIONS`. Stations are only read when a mountain names them.
- For the region's first station, check the time its daily values are stamped in against its hourly readings
  (see the note at the top of `sources/snotel.py`) and confirm `Region.std_offset_h` is right for it.

A region uses its own fitted files where they exist and the Sierra's otherwise: `models/bias_<region>.json` (the
water correction; with none, the models are used as they are), `weights_<region>.json`, `snow_phase_<region>.json`
and `snow_ratio_<region>.joblib`. The Cascades have the first three and the Tetons all four.

Until those files exist the pipeline uses the models as they are with the Sierra's curve, ratio and weights, so
the region can be built before it is fitted. Fitting is step 1e and is part of adding a region.

### 1c. Edit `snow/tahoe_snow/config.py`

```python
# in REGIONS
"saltlake": Region("saltlake", "Salt Lake", "America/Denver", 7, 12, ("UAC",)),

# in RESORTS, with region="saltlake" on every one
Resort("alta", "Alta", <lat>, <lon>, _ft(<base>), _ft(<summit>), "<triplet or None>", "Ikon", region="saltlake"),
```

Avalanche centers by region (all on `api.avalanche.org`, checked 2026-11-22):

| Region | Centers |
|---|---|
| Seattle | `NWAC` |
| Salt Lake | `UAC` |
| Tetons | `BTAC` |
| New England | `MWAC` |
| Alaska | `CNFAIC`, `HPAC` |

For any other region, see whether its center answers:
`https://api.avalanche.org/v2/public/products/map-layer/<CENTER>` returns a list of zones if it does. Then open one zone on the
Avalanche tab in the preview before trusting it: Colorado's center answers with seven zones all named "CAIC zone",
which has not been tried. A center whose zones do not show a forecast is left out (an empty tuple).

### 1d. Test, push, wait

```bash
cd snow && python -m pytest -q
```

`test_the_configured_regions_fit_the_daily_allowance` is the one that matters. Update
`test_the_home_regions_cost_what_the_ledger_measured` only if it was written against the total; it should count the
home regions alone.

Commit (`snow: the forecast covers Salt Lake: eight mountains, built twice a day`), push, and restart the collector
(Global Constraints): a run in progress keeps the configuration it started with. Within one pass the collector sees
the new region has no file and builds it. The page does not offer a region until its first forecast is published,
so nothing shows early. Confirm:

```bash
gh api "repos/N955PK/livefreeandfly/contents/forecast?ref=snow-data" -q '.[].name'
```

lists `<region>.json`. Then read the run's log for that pass: every mountain printed a line and none said `FAILED`.
A mountain fails when no model gives it precipitation; the usual cause is a wrong coordinate.

Fetch the real file for the second push (never committed):

```bash
curl -s https://raw.githubusercontent.com/N955PK/livefreeandfly/snow-data/forecast/<region>.json > snow/data/forecast/<region>.json
```

```bash
curl -s https://raw.githubusercontent.com/N955PK/livefreeandfly/snow-data/index.json > snow/data/index.json
```

### 1e. Fit the region's own models

Only for a region with snow sensors; New England has none and uses the Sierra's throughout. None of this calls the
metered Open-Meteo API: the fits read Open-Meteo's archive on S3 and the sensors from NRCS. `cascades-snow-model.md`
records how each was done for the Cascades and what it cost; the Tetons, the Wasatch and Colorado followed it. In order:

1. **Water correction.** Add the region's stations and a box to `calibrate.REGIONS`, then `pairs`, `held_out_test`
   on each of the last three winters, and `fit_and_save` (`models/bias_<region>.json`). Keep it only if corrected
   beats raw on the held-out winters. A station whose own curve overshoots its held-out winter goes in
   `calibrate.POOLED_ONLY`. A peak whose sensor sits far below it is left uncorrected (`Resort.corrected=False`).
   State pillows (CDEC) measure snow alone, with no gauge beside them. Where they sit low enough to be rained on,
   the models look wet against them and no correction can be fitted: check the models against the pillows on
   all-snow days and on days above freezing before believing a fit (Shasta: 1.1 times and 2.7 times; nothing kept).
2. **Blend weights.** `calibrate.save_weights` from the same held-out table (`models/weights_<region>.json`).
3. **Rain or snow.** `train.fit_region_phase` (`models/snow_phase_<region>.json`).
4. **Snow ratio.** `train.check_region_ratio` first, against snowfall measured by hand near the region. Refit
   (`train.fit_region_ratio`) only if that beats the Sierra's model at stations left out of the fit; either way
   save the check (`models/snow_ratio_check_<region>.json`).
   The refit is the Sierra's days with the region's added. Where the Sierra's days still pull it off (the Wasatch,
   where it ran an inch deep), give the region's days more weight in `train.REGION_DAY_WEIGHT` and check again.

Sean wants each file saved even where it barely differs from the Sierra's, as the record that it was fitted there.
Write the results into the testing page (2f) and add the region's sections to the scorecard (`verify.py`, beside
`seattle_sections`, `tetons_sections`, `wasatch_sections` and `colorado_sections`). Push, and restart the collector so the next build uses them. The Sensor
corrections list on the page follows the published index, so it reads Corrected as soon as the index is rebuilt.

## 2. Second push: the page

### 2a. Terrain

`snow/tools/build_terrain.py`, in `REGIONS`:

```python
"saltlake": {"box": (<south>, <north>, <west>, <east>), "max_m": <just above the highest peak in the box>, "columns": <width>},
```

- The box holds every mountain with about 25 km of margin. `columns` keeps a cell near 0.39 km:
  `columns = box width in km / 0.39`, where a degree of longitude is `111.32 x cos(latitude)` km. Tahoe is 420, the
  Eastern Sierra 640; stay at or under 640 and let the cell grow instead (New England's box is 262 x 284 km at
  640 columns, a 0.41 km cell and an 880 KB file).
- `max_m` clips bad pixels in the source tiles. Too low flattens real summits.
- For a round map, make the box a square around the circle and give the region a `discKm` a kilometre **under**
  half the built terrain's shorter side (`width_km`, `height_km` in its `.json`). A disc that reaches past the
  terrain is faded at the square's edges too, and the map comes out a rounded square instead of a circle.

```bash
cd snow && python tools/build_terrain.py <region>
```

It needs `requests`, `Pillow`, `numpy` and `scipy` and reads public elevation tiles (no key, not Open-Meteo). The
forecast's own interpreter may lack Pillow; a throwaway virtual environment with those four is enough. It writes
`data/terrain-<region>.bin` and `.json`. Commit both. Then read the heightmap back and print its height at each
mountain's coordinates: every one should sit between that mountain's base and summit.

Where the region has the sea, or a lake that sits above the lowest ground in the box, mark it `"water": True`: the
tool then also writes `data/terrain-<region>.water.bin`, and the map draws water from that instead of from level
ground. `python tools/build_terrain.py <region> --locator-water` prints the sea's outline for the avalanche
locator (2c).

### 2b. Road lines

`snow/tools/build_roads.py`, in `ROUTES`: the highways to draw, as `{"<ref as OpenStreetMap writes it>": "<label on
the shield>"}`. Refs look like `"I 80"`, `"US 189"`, `"UT 210"`, `"WA 410"`. Choose the roads someone drives to
these mountains: the interstates and the canyon or pass roads, ten to fourteen in all.

```bash
cd snow && python tools/build_roads.py <region>
```

Writes `data/roads-<region>.json`; commit it. `CREST` is only for a map that should drop one side of a range; leave
the region out of it. The tool asks the public Overpass servers, which are sometimes at capacity for hours: try
again later. Until the file exists the map draws no road lines and hides the Shields button, so the page can ship
without it. A road whose number has a prefix the map has not drawn before (a new state) gets a plain white
marker; a drawn outline for it is an addition to the shield shapes in `map3d.js`.

Add the terrain files and the roads file to `SHELL` in `snow/sw.js`, beside the other regions', so they are kept
for use with no signal.

### 2c. The region's entry in `snow/index.html`

In the `REGIONS` table near the top of the script:

```js
saltlake: {name: "Salt Lake", terrain: "data/terrain-saltlake", roads: "data/roads-saltlake.json",
  center: [<lat>, <lon>], waterM: <metres>, pick: "<the mountain it opens on>",
  avalanche: [{id: "UAC", name: "Utah Avalanche Center", url: "https://utahavalanchecenter.org/"}]},
```

| Field | What it does |
|---|---|
| `name`, `short` | The menu's name; `short` (optional) is used beside the app's name when `name` is long |
| `terrain`, `roads` | The files from 2a and 2b |
| `center` | Latitude and longitude of the middle of the box |
| `waterM` | Ground at or below this height is drawn as water. A lake's surface height, or 0 for the sea. If the region has neither, a value below the lowest ground in the box |
| `pick` | The mountain the region opens on when nothing is starred |
| `avalanche` | The centers from 1c, with the center's name and site; the first is the one the tab opens on |
| `lake` (optional) | `{name, lat, lon}`: one water label on the map (Great Salt Lake, Jackson Lake, Lake Champlain, Turnagain Arm) |
| `look`, `discKm`, `zoom`, `turnDeg` (optional) | The opening view: where the camera looks if not at `center`, how far out the ground is drawn (default serves a Tahoe-sized box; 115 for one the Eastern Sierra's size; 190 for New England's), how far in the camera starts (it cannot start further out than about `1.5 x discKm / 72`), and its turn in degrees |
| `land` (optional) | The ground's colours by height, where forest-green is wrong (see the Eastern Sierra's and New England's) |
| `floorM`, `lowlandM` (optional) | The map raises all ground below 1,150 m to that height, and only counts level ground above 400 m as a lake: right for the Sierra, wrong anywhere low. A region with summits near or under 1,500 m, or one that reaches the sea, sets both to 0 |
| `rev` (optional) | `"?v=2"`; bump it whenever the terrain or road files are rebuilt, so phones fetch the new ones |

Leave out `chainFeeds` and `closureFeeds`: there is no road status outside California and Nevada. A state whose
route numbers are not California's takes `plainStateRoutes: true`.

Also in `index.html`, all part of the job:
- **Sub-areas** (`areas` in the region's entry): `[{key, name, short?, mountains: [...]}]`, one pill each beside
  "All" under the map, for a region with more than about ten mountains or more than one range or state. Order each
  list north to south. Every mountain in the region is in exactly one list.
- **`PEAK_AT`**: `{key: [lat, lon]}` for a backcountry peak whose forecast point is on its flank, so its stake
  stands over the summit.
- **`AVY_AREAS` and `AVY_AREA`**: the avalanche menu groups zones by part of the country. Add the group's name to
  `AVY_AREAS` and each state the region's centers cover to `AVY_AREA`. Each center in the region's `avalanche`
  list carries its `state`.
- **`LOCATORS`**: a frame for the small map on the Avalanche tab that shows where the zone is, drawn in the same
  style and with the same markers as California's: the zones' outlines, the sea or big lake where there is one
  (from `--locator-water`), and the prominent mountain of each zone named, with names set to the side so they do
  not sit on the zones.
- **`SHORT`** and the region's `short`: a shorter name for a long one, for table rows and the Favorites table
  (New England is "NE").
- **`STATUS_PAGES`**: the link to each resort's own status page.

### 2d. Check it in the preview

`http://localhost:8765/snow/?v=<bump>` at 393x852, light and dark:

- The region is in the menu; choosing it loads one file and no console errors.
- **Map:** every label that shows sits on its mountain, not beside it. The roads lie in the valleys. The opening
  view takes in all the mountains; tune `look`, `zoom`, `turnDeg`, `discKm` until it does. Where mountains crowd,
  the map hides some labels until one is selected; check that selecting each brings its label up. Water is where
  water is, and low ground is not one flat colour.
- **Region tab:** every mountain has a row with snow figures; the day columns start on the mountains' own today.
- **Mountain tab:** the hourly chart's clock is the mountain's own time. A mountain with a sensor shows measured
  snow; one without reads Uncorrected. The lift section shows the same empty state a backcountry spot does.
- **Avalanche tab:** the zone under the selected mountain opens, with its danger signs and photos. Where the
  mountains sit outside every zone (New England: the one zone is the Presidential Range), the region's first zone
  opens as general reading and no resort is marked as uncovered. Check a center that is out of season: no rating,
  nothing broken.
- Star one of the new mountains: it appears in Favorites next to mountains from other regions.
- **Sub-area pills:** each frames its mountains with every name showing; where two names would collide one sits to
  the side of its stake.
- **Menus:** the region is in A-to-Z order in the region menu (Favorites first), in the Sensor corrections list and
  in the explanations; its avalanche zones are under their group.
- **Lifts:** each resort with a reader shows its lift and trail counts and its report; one without says so plainly.

Use a browser tab of your own for this (Sean uses the main preview tab and has his own saved choices), and put back
anything you change.

### 2f. The words

- **How the forecast is made:** a paragraph for the region beside Tahoe's, Eastern Sierra's and the others',
  saying what is fitted there and what is borrowed from the Sierra, and anything read differently (lower pressure
  levels). The Status paragraph says which of the region's resorts have their lifts read and which cannot be.
- **How it is tested:** under each topic (snow ratio, rain or snow, water), a heading for the region with its
  held-out results, or one line under "What is not tested yet" if nothing was fitted. Say what was tried and did
  not win; do not recount errors that were made and fixed along the way.
- **`og:description`** in the page's head names the region.
- Plain whole sentences, no jargon, no avalanche or travel disclaimers. The sensor tags are exactly Corrected,
  Low sensor and Uncorrected.

### 2e. Push

Commit (`snow: Salt Lake is on the page, with its map, roads and avalanche forecast`) and push. The next morning,
read the ledger on the data branch (`archive/usage.json`): the last day's calls are under 9,900 and nothing was
rate limited.

## 3. Lifts and the resort's report

Part of adding a region: do it for every resort. A mountain's lift status comes one of three ways:

1. **Alterra's feed** (many Ikon mountains): open the resort's own mountain-report page with the browser's network
   panel and look for a request to `mtnpowder.com/feed?resortId=<N>`. If there is one, the phone can read it
   directly: add the mountain to `LIFT_FEEDS` and `STAKES` in `index.html` and to `MOUNTAINS` in `reports.py` and
   `holds.py`. Do not guess an id.
2. **Vail's pages** (Epic mountains): the phone cannot read them. Add the mountain to
   `tahoe_snow/sources/resort_status.py`, which the collector runs every pass and publishes on `snow-lifts`.
3. **Anything else**: a reader of its own under `tahoe_snow/sources/<key>.py` that knows the page (`URL`, or `URLS`
   for more than one request) and reads it (`parse(page, now)`), with a saved copy of the page in `tests/fixtures/`
   and a test. It gives the Ikon feed's shape: lifts, trails, and a `SnowReport` with base depth and new snow where
   the site has them. It fails on a page it does not recognise instead of giving wrong numbers. Add the module to
   `MODULES` in `sources/independents.py`, which runs them all each pass, gives a depth that comes as a range its
   middle, and leaves out a closed mountain's undated or old report (several sites keep last season's figures up
   until they open). A new region can have a runner of its own beside it; then add its line to the collector's pass
   in `snow-collect.yml` and its name to the list in `collect.py`. If the site sits behind a bot check, stop there:
   the app does not work around those, and the Status paragraph says the resort has none.

Finding the source: look at the resort's conditions page for the request it makes or the JSON in its HTML
(`__NEXT_DATA__`, a `wp-admin/admin-ajax.php` call, a framed page on another host). The Liftie project's
`lib/resorts/<name>/` often records the page and where the statuses are, though its addresses go stale. Thirteen
resorts' worth of this goes fastest as three or four subagents, each writing only new files, with the runner and the
page wired here afterwards.

On the page, for each resort that is read: `LIFT_FEEDS`, `FEED_LOADERS` (`publishedFeed("<file>.json", key)`),
`STATUS_PAGES`, and `STAKES` when its report gives a base depth. Where the region has no snow sensors, those depths
are what turns the map white, counted at half weight because they are mostly snow made on the trails.

`holds.py` and `reports.py` assume Pacific time; give them the region's zone before adding a mountain outside it.

## What to tell Sean when a region ships

One short message, answer first: the region and its mountains, which share weather and with whom, how many calls
a day the whole app now plans to spend out of 9,900, which mountains are Corrected, Low sensor or Uncorrected, what
was fitted and whether it beat the Sierra's, which resorts have lift status and which could not be read, and every
checklist line that is not done or could not be checked (nothing is ever checked on a real phone; say so).

## Working rules that apply the whole way

- Push to `main` as each piece is done; do not batch. Commit messages are one plain sentence starting `snow:`.
- Other sessions commit in this checkout. Commit with explicit paths, check `git log origin/main..HEAD` before
  pushing, and push only your own commits. Where another session has uncommitted edits in a file you need, make
  your change as a patch against `HEAD` and apply it to the index and the working tree.
- A running collector keeps the code it started with. After pushing pipeline or workflow changes, cancel its run
  (`gh run cancel <id>`; it restarts itself if it had run ten minutes, otherwise
  `gh workflow run snow-collect.yml --ref main`). Do not cancel during a build.
- Never run the forecast locally or call Open-Meteo's metered API. Sensor, lift, map and elevation reads are fine.
- Never commit `snow/data/forecast*`, `snow/data/index.json` or the feed copies used for the preview.
- Requests to outside services carry a generic client name and nothing about Sean or the project.
