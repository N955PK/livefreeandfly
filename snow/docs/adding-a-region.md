# Adding a region to Turbo Snow

One pass of this guide adds one region. It assumes Tasks 1 to 6 of `2026-11-22-regions-plan.md` are done (regions
are a table, each has its own forecast file, the page loads regions one at a time). Read the plan's **Global
Constraints** first; they all apply here.

It is **two pushes**. The first tells the forecast about the region, and the collector builds real data within one
pass. The second teaches the page to show it, checked against that real data. The page ignores a region it has no
entry for, so nothing shows between the two.

Throughout, `<region>` is the key: lower case, no spaces (`saltlake`).

## 0. Check it fits

Each mountain costs 51.9 Open-Meteo calls a run (more where the region reads extra low pressure levels). A region is
built at fixed hours on its own clock (`Region.at`; `every_h` is 24 over their number): the western regions four
times a day, New England twice. At twice a day that is **103.7 calls a mountain a day**. A mountain within about
8 km of another can take its neighbour's weather instead of asking for its own (`Resort.weather_from`), and then
costs nothing.
The day's ceiling is 8,500. The test in step 1 enforces it; do the sum first anyway:

```
calls a day = (Tahoe + Eastern Sierra mountains) x 4 x 51.9  +  (all other mountains) x 2 x 51.9
```

A region whose mountains reach below about 1,450 m needs pressure levels under 850 hPa, or every height below that
is given the 850 hPa temperature and rain is called snow. Give its `Region` `low_levels=(950, 925, 900)` as Seattle
has, or New England's `(1000, 975, 950, 925, 900)` (900 hPa is near 990 m, 925 near 760 m, 950 near 540 m, 975 near
320 m, 1000 near 110 m; take only the ones the lowest base needs). Each extra level costs 2.51 calls a mountain a
run, and `usage.planned()` counts it: with both regions the plan is 7,838 calls a day of 8,500.

One region is built in one collector pass. Eight mountains take about a minute and a half; New England's fourteen
take about two and a half, which is the most a region should hold. A bigger area is two regions.

## 1. First push: the forecast

### 1a. Pick the mountains and get their numbers

For each mountain you need: a key (lower case, no spaces, unique across all regions), its name, latitude and
longitude **at mid-mountain**, base and summit elevation in metres, and its pass (`Ikon`, `Epic`,
`Mountain Collective`, `Indy`, `Independent`, or `Backcountry`).

- Elevations: the resort's own published base and summit, or OpenSkiMap's statistics. Feet go through `_ft()`.
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

There is no fitted correction for a new region (`models/bias_<region>.json` does not exist), and the pipeline
handles that: the models are used as they are. Fitting one is a separate job (`calibrate.py`, which needs the
region's stations and a box added to its `REGIONS`) and is not part of adding a region.

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

```bash
cd snow && python tools/build_terrain.py <region>
```

It needs `requests`, `Pillow`, `numpy` and `scipy` and reads public elevation tiles (no key, not Open-Meteo). The
forecast's own interpreter may lack Pillow; a throwaway virtual environment with those four is enough. It writes
`data/terrain-<region>.bin` and `.json`. Commit both. Then read the heightmap back and print its height at each
mountain's coordinates: every one should sit between that mountain's base and summit.

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

Leave out `chainFeeds` and `closureFeeds`: there is no road status outside California and Nevada.

Also in `index.html`, only if wanted:
- `SHORT`: a shorter name for a long one, for the Region tab's rows.
- The resort-report and webcam link tables: a mountain missing from them simply has no link.

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

### 2e. Push

Commit (`snow: Salt Lake is on the page, with its map, roads and avalanche forecast`) and push. The next morning,
read the ledger on the data branch (`archive/usage.json`): the last day's calls are under 8,500 and nothing was
rate limited.

## 3. Later, per mountain: lifts and the resort's report

Not part of adding a region. When wanted, a mountain's lift status comes one of three ways:

1. **Alterra's feed** (many Ikon mountains): open the resort's own mountain-report page with the browser's network
   panel and look for a request to `mtnpowder.com/feed?resortId=<N>`. If there is one, the phone can read it
   directly: add the mountain to `LIFT_FEEDS` and `STAKES` in `index.html` and to `MOUNTAINS` in `reports.py` and
   `holds.py`. Do not guess an id.
2. **Vail's pages** (Epic mountains): the phone cannot read them. Add the mountain to
   `tahoe_snow/sources/resort_status.py`, which the collector runs every pass and publishes on `snow-lifts`.
3. **Anything else**: a reader of its own under `tahoe_snow/sources/`, as `homewood.py` and `boreal.py` are, added
   to the collector's pass. If the site sits behind a bot check, stop there: the app does not work around those.

`holds.py` and `reports.py` assume Pacific time; give them the region's zone before adding a mountain outside it.

## What to tell Sean when a region ships

One short message: the region and its mountains, how many calls a day the whole app now spends out of 8,500, which
mountains have a sensor and which do not, and anything on the list in 2d you could not check.
