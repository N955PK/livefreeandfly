# More Regions and Favorites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turbo Snow forecasts several regions on their own schedules inside the Open-Meteo free allowance, and the page gains a Favorites list that spans regions.

**Architecture:** A `Region` table in `config.py` is the single list of regions (time zone, interval, avalanche centers). The pipeline builds one region at a time into `forecast/<region>.json` plus an `index.json` of every mountain; the collector builds the most overdue region each pass. The page loads the index, then only the regions it needs; "Favorites" is a list that borrows the selected mountain's region for the map, roads and avalanche tabs.

**Tech Stack:** Python 3.11 (pandas, numpy; pytest), one static page (`snow/index.html`, `snow/map3d.js`, no build step), GitHub Actions (`.github/workflows/snow-collect.yml`), data on the `snow-data` branch.

**Spec:** `snow/docs/2026-11-22-regions-design.md`. Per-region steps: `snow/docs/adding-a-region.md`.

## Global Constraints

- Allowance: configured mountains x runs a day x 51.9 calls must be at most 8,500 a day. Home regions (`tahoe`, `mammoth`) every 6 hours; every new region every 12.
- **Never call Open-Meteo from a test or from your own machine.** Tests use fixtures and monkeypatched fetches. Do not run `python -m tahoe_snow run` locally without asking Sean; real data for a new region comes from the collector after a push (see the guide).
- Published data keeps today's shape per mountain. New fields are additive (`tz`). `forecast.json` (Tahoe + Eastern Sierra) keeps being written.
- Tahoe's and the Eastern Sierra's numbers must not change: same requests, same time zone, same corrections.
- Imports at the top of each Python file. Standard-library-only modules (`reports.py`, `holds.py`, `collect.py`, `avybundle.py`, `sources/*` used by the collector's first pass) stay standard-library-only.
- Page rules: things you can tap are true pills, static things are squared (6px; content cards 11px). No colour flash on press or selection. Whole plain sentences in any copy, no jargon.
- Commit straight to `main`, one commit per task, message a plain sentence starting `snow:`, ending with the `Co-Authored-By` trailer the session gives you. Never commit `assets/logo-concept.v*.png`, `cabin/skier-logo-512.png`, `.claude/launch.json`.
- Tests: `cd snow && python -m pytest -q` (69 pass before this plan). Page checks: the `site` preview (`http://localhost:8765/snow/?v=N`, bump `N` to reload) at 393x852, light and dark.
- After a workflow change, the running collector must be restarted to pick it up: cancel the run in progress; if it had run under ten minutes it will not restart itself, so `gh workflow run snow-collect.yml --ref main`.

## Review Focus

1. **A region with nothing but a forecast.** No lake, no road feeds, no lift feeds, no sensor (New England). The map must build, the block of map buttons must still appear (today it waits for the Roads button), and the opening screen must lift. Test in Task 5.
2. **A day boundary in another time zone.** A New England mountain's "today" starts three hours before Tahoe's; at 9 pm Pacific its first forecast day is tomorrow's date in Pacific terms. Test in Task 1.
3. **A favorite whose mountain has gone** (renamed key, region removed, region file failed to load). It is skipped, not an error, and stays saved. Test in Task 6.
4. **Offline with several regions.** With no signal the page shows the saved copy of each region it has, and says so; a region never opened is reported as needing a signal, not a blank page. Test in Task 4.
5. **One region failing in the collector.** Open-Meteo refusing one region's run must not stop the others, must not publish an empty file over a good one, and must not be retried for half an hour. Test in Task 3.

---

### Task 1: The region table and per-region time

**Files:**
- Modify: `snow/tahoe_snow/config.py` (add `Region`, `REGIONS`; `Resort.region` stays a key into it)
- Modify: `snow/tahoe_snow/pipeline.py` (`TZ` constant removed; `local_days`, `day_part`, `resort_forecast` take the zone), `snow/tahoe_snow/blend.py` (callers pass `tz`)
- Modify: `snow/tahoe_snow/avybundle.py`, `snow/tahoe_snow/collect.py` (`CENTERS` derived from `REGIONS`)
- Modify: `snow/tahoe_snow/usage.py` (add `planned`)
- Test: `snow/tests/test_regions.py` (new)

**Interfaces:**
- Produces:
  - `config.Region(key: str, name: str, tz: str, std_offset_h: int, every_h: int, avalanche: tuple[str, ...])`, frozen dataclass. `std_offset_h` is hours behind UTC in standard time (Pacific 8, Mountain 7, Alaska 9, Eastern 5).
  - `config.REGIONS: dict[str, Region]` with exactly `tahoe` ("Tahoe", `America/Los_Angeles`, 6, `("SAC",)`) and `mammoth` ("Eastern Sierra", `America/Los_Angeles`, 6, `("ESAC", "BAC")`).
  - `config.resorts_in(region: str) -> list[Resort]`.
  - `config.avalanche_centers() -> tuple[str, ...]`: every region's centers, in region order, no repeats.
  - `usage.CALLS_PER_RESORT_RUN = 51.9` and `usage.planned(regions=REGIONS, resorts=RESORTS) -> float`: calls a day the configuration will spend (`sum(len(resorts_in(r)) * 24 / r.every_h * CALLS_PER_RESORT_RUN)`).
  - `usage.PLAN_LIMIT = 8500`.
  - Each published mountain gains `"tz": <its region's tz>`.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_resort_belongs_to_a_configured_region():
    assert {r.region for r in config.RESORTS.values()} <= set(config.REGIONS)

def test_the_configured_regions_fit_the_daily_allowance():
    assert usage.planned() <= usage.PLAN_LIMIT

def test_the_home_regions_cost_what_the_ledger_measured():
    # 21 mountains, 4 runs a day, 1,089 calls a run
    assert round(usage.planned()) == round(21 * 4 * 51.9)

def test_avalanche_centers_come_from_the_regions_without_repeats():
    assert config.avalanche_centers() == ("SAC", "ESAC", "BAC")

def test_a_day_is_the_mountains_own_day():
    hours = pd.date_range("2026-12-01 03:00", periods=4, freq="h")       # UTC
    assert list(pipeline.local_days(hours, "America/Los_Angeles").strftime("%Y-%m-%d")) == ["2026-11-30"] * 4
    assert list(pipeline.local_days(hours, "America/New_York").strftime("%Y-%m-%d")) == ["2026-11-30", "2026-11-30", "2026-12-01", "2026-12-01"]
```

- [ ] **Step 2: Run them and see them fail** (`python -m pytest tests/test_regions.py -q`: `AttributeError: REGIONS`).
- [ ] **Step 3: Add `Region`, `REGIONS`, `resorts_in`, `avalanche_centers` to `config.py`; `planned` and the two constants to `usage.py`.**
- [ ] **Step 4: Thread the zone through the pipeline.** `local_days(index, tz)`, `day_part(..., tz)`, and every `tz_localize(TZ)`/`tz_convert(TZ)` in `pipeline.py` use `REGIONS[resort.region].tz`; `blend.robust_mean` and `blend.local_day_totals` already take `tz` and must be passed it. Add `"tz"` to the payload dict in `resort_forecast` beside `"region"`. `holds.py` and `reports.py` keep `America/Los_Angeles`: they only cover Pacific mountains.
- [ ] **Step 5: Sensor days.** SNOTEL's daily values are midnight readings in the station's local standard time. `season.PST_OFFSET_H = 8` and `pipeline.snotel_offset_h()` assume Pacific. Make both take the offset of the region of the mountain the station is paired with (`Region.std_offset_h`); Tahoe and Eastern Sierra results must be byte-for-byte what they were (`test_forecast_parts.py` and the season tests prove it). When the first Mountain-time station is added (Task 7), confirm the offset against that station's hourly readings before trusting its daily gains, as the note at the top of `sources/snotel.py` did for Pacific.
- [ ] **Step 6: Replace both `CENTERS = ("SAC", "ESAC", "BAC")` tuples** (`avybundle.py`, `collect.py`) with `config.avalanche_centers()`. Check first that `config.py` imports nothing outside the standard library (it does not today); keep it so.
- [ ] **Step 7: Run the whole suite** (`python -m pytest -q`, all pass, including `test_forecast_parts.py` unchanged).
- [ ] **Step 8: Commit** (`snow: regions are a table in the configuration, each with its own time zone and forecast interval`).

---

### Task 2: One forecast file per region, and an index

**Files:**
- Modify: `snow/tahoe_snow/pipeline.py` (`run`, `refresh_season`), `snow/tahoe_snow/__main__.py`
- Modify: `snow/tahoe_snow/verify.py` and anything else that reads `archive/YYYY/MM/*.json` (grep `archive` in `tahoe_snow/` and `tools/`)
- Test: `snow/tests/test_region_files.py` (new)

**Interfaces:**
- Consumes: `config.REGIONS`, `config.resorts_in`, `Region.every_h` (Task 1).
- Produces:
  - `pipeline.run(region: str, now=None) -> dict`: builds only that region. Writes `DATA/forecast/<region>.json` (exactly today's top-level shape: `generated_utc`, `published_utc`, `resorts`, `season_curves`, `usage`, ...), rewrites `DATA/index.json`, rewrites `DATA/forecast.json` as the merge of `forecast/tahoe.json` and `forecast/mammoth.json` when both exist, and writes the archive file `archive/YYYY/MM/DD_HHz_<region>.json`.
  - `pipeline.write_index() -> dict`: `{"regions": {key: {"name", "tz", "every_h", "published_utc" | None}}, "resorts": [{"key", "name", "region", "kind", "pass", "lat", "lon", "tz", "station", "weak_station_match"}]}` for every configured mountain; `published_utc` read from each region file that exists.
  - `pipeline.due(now=None) -> str | None`: the key of the region whose file is oldest relative to its interval (`age / every_h` largest) among those at or past their interval; a region with no file is the most overdue; `None` when nothing is due.
  - CLI: `python -m tahoe_snow run [region]` (no region: every region, for use by hand), `python -m tahoe_snow due` (prints the key or nothing; always exits 0).
  - If every mountain of the region fails, `run` raises `SystemExit` and writes nothing, so a good file is never replaced by an empty one.

- [ ] **Step 1: Write the failing tests.** Monkeypatch `pipeline.resort_forecast` to return a small payload and no archive rows, `pipeline.add_season` to return `{}`, and `config.DATA`/`pipeline.DATA` to `tmp_path`.

```python
def test_a_run_writes_only_its_own_region(tmp_path, stubbed):
    pipeline.run("mammoth", NOW)
    assert sorted(p.name for p in (tmp_path / "forecast").iterdir()) == ["mammoth.json"]
    assert {r["region"] for r in json.loads((tmp_path / "forecast/mammoth.json").read_text())["resorts"]} == {"mammoth"}

def test_the_index_lists_every_mountain_and_when_each_region_was_built(tmp_path, stubbed):
    pipeline.run("tahoe", NOW)
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["resorts"]) == len(config.RESORTS)
    assert index["regions"]["tahoe"]["published_utc"] and index["regions"]["mammoth"]["published_utc"] is None

def test_the_old_single_file_is_still_written_once_both_home_regions_exist(tmp_path, stubbed):
    pipeline.run("tahoe", NOW); assert not (tmp_path / "forecast.json").exists()
    pipeline.run("mammoth", NOW)
    assert len(json.loads((tmp_path / "forecast.json").read_text())["resorts"]) == 21

def test_the_most_overdue_region_is_due_first(tmp_path, stubbed):
    assert pipeline.due(NOW) in config.REGIONS                      # nothing built yet
    pipeline.run("tahoe", NOW); pipeline.run("mammoth", NOW)
    assert pipeline.due(NOW + timedelta(hours=5)) is None
    assert pipeline.due(NOW + timedelta(hours=6, minutes=1)) in ("tahoe", "mammoth")

def test_a_region_where_every_mountain_fails_keeps_its_last_file(tmp_path, stubbed, monkeypatch):
    pipeline.run("mammoth", NOW); before = (tmp_path / "forecast/mammoth.json").read_text()
    monkeypatch.setattr(pipeline, "resort_forecast", raising(RuntimeError("refused")))
    with pytest.raises(SystemExit): pipeline.run("mammoth", NOW)
    assert (tmp_path / "forecast/mammoth.json").read_text() == before
```

- [ ] **Step 2: Run and see them fail.**
- [ ] **Step 3: Implement `run(region)`, `write_index`, `due`, and the CLI.** `forecast.json`'s merge takes `generated_utc`/`published_utc` from the older of the two home files (so the page's staleness colour stays honest) and concatenates `resorts`; `season_curves` are merged by key.
- [ ] **Step 4: Move the archive readers to the new file names.** `DD_HHz_<region>.json`; a reader must still accept the old `DD_HHz.json` files that are on the data branch for three more weeks.
- [ ] **Step 5: `refresh_season`** rewrites each existing region file in place and then the merged file.
- [ ] **Step 6: Run the whole suite, commit** (`snow: each region's forecast is built and published as its own file, with an index of every mountain`).

---

### Task 3: The collector builds the most overdue region each pass

**Files:**
- Modify: `.github/workflows/snow-collect.yml` (the `forecast()` shell function and the header comment)

**Interfaces:**
- Consumes: `python -m tahoe_snow due`, `python -m tahoe_snow run <region>` (Task 2).
- Produces: the `snow-data` branch holds `index.json`, `forecast/<region>.json`, `forecast.json`, `scorecard.json`, `archive/`.

- [ ] **Step 1: Rewrite `forecast()`.** Each pass: fetch `snow-data` and extract the **whole tree** into `$code/data` (today only `archive` is extracted; the other regions' files must survive a publish of one). Ask `python3 -m tahoe_snow due`; nothing printed means return. Keep the half-hour `tried` guard and the `budget` gate exactly as they are. Run `python3 -m tahoe_snow run "$region" && python3 -m tahoe_snow prune`. Publish `index.json`, `forecast.json` (if present), `scorecard.json`, `forecast/`, `archive/` as the branch's one commit. The age test on the branch's commit date (the `-lt 360`) goes: `due` decides.
- [ ] **Step 2: Syntax check.** Extract the step's script and run `bash -n` on it:
  `python3 -c "import yaml; print(yaml.safe_load(open('.github/workflows/snow-collect.yml'))['jobs']['collect']['steps'][3]['run'])" > /tmp/loop.sh && bash -n /tmp/loop.sh`
- [ ] **Step 3: Commit, push, restart the collector** (see Global Constraints).
- [ ] **Step 4: Verify on the branch.** Within two passes: `gh api repos/N955PK/livefreeandfly/contents/forecast?ref=snow-data -q '.[].name'` lists `tahoe.json` and `mammoth.json`; `forecast.json` still loads on the live page; the run's log shows one region per pass and no `::error::`. Kill-test for Review Focus 5: confirm in the log that a pass with nothing due prints nothing and costs no Open-Meteo requests.

---

### Task 4: The page loads the index and only the regions it needs

**Files:**
- Modify: `snow/index.html` (the loader around `publishedForecast`/`liveForecast`, `pickRegion`, `setRegion`, `fixTimes`, and every use of the constant `TZ`)
- Modify: `snow/sw.js` (the `data/forecast.json` exemption covers `data/index.json` and `data/forecast/*.json`)

**Interfaces:**
- Consumes: `index.json`, `forecast/<region>.json` (Task 2/3); each mountain's `tz`.
- Produces (page globals later tasks use):
  - `index`: the parsed `index.json`. `data.resorts`: every mountain of every region loaded so far. `data` keeps `generated_utc`/`published_utc` of the region on screen.
  - `async loadRegion(key) -> boolean`: fetches and merges one region file once (by commit SHA as `publishedForecast` does now; `data/forecast/<key>.json` on localhost); saves it in the `sierra-snow-data` cache under `forecast/<key>`; on failure falls back to that saved copy and sets `offlineCopy`; returns false if neither exists.
  - `tzOf(resort) -> string`: `resort.tz || "America/Los_Angeles"`.
  - `setRegion(key)` becomes async: awaits `loadRegion(key)` before rendering. If it returns false the region stays as it was and a line of text says the region needs a signal.

- [ ] **Step 1: Loader.** Load `index.json` first (fall back to the saved copy; if there is neither, load `forecast.json` exactly as today so an old data branch still works). `pickRegion` chooses from `index.regions` that the page's own `REGIONS` table also knows. Then `loadRegion(region)`.
- [ ] **Step 2: Replace the constant `TZ`.** Every `timeZone: TZ` (about twenty: grep `TZ`) becomes `tzOf(...)` of the mountain being drawn; places with no mountain in hand (`localHour`, the map clock) use the selected mountain's. Delete `const TZ`. The two Pacific-only readers of the Ikon feed's wall-clock stamps (`["-08:00", "-07:00"]`) stay as they are.
- [ ] **Step 3: Everything that lists all regions' mountains reads `index.resorts`**: `renderQuality` (the sensor sheet), the mountain chooser. They must not need a region's forecast to be loaded.
- [ ] **Step 4: Check in the preview.** Put real files in place first: `mkdir -p snow/data/forecast && for r in tahoe mammoth; do curl -s https://raw.githubusercontent.com/N955PK/livefreeandfly/snow-data/forecast/$r.json > snow/data/forecast/$r.json; done; curl -s https://raw.githubusercontent.com/N955PK/livefreeandfly/snow-data/index.json > snow/data/index.json` (add `data/forecast/` and `data/index.json` to `snow/.gitignore` beside `data/forecast.json`; they are never committed). Then: opens on Tahoe with one region file fetched (network panel); switching to Eastern Sierra fetches the second once; switching back fetches nothing; no console errors; the charts' clock labels are unchanged from the live site.
- [ ] **Step 5: Offline check (Review Focus 4).** With both regions opened once, block the network in the preview (`javascript_tool`: override `fetch` to reject for raw.githubusercontent.com and reload is not possible offline locally, so instead call `loadRegion` with fetch stubbed to reject): the saved copy is returned and the "Offline." note shows; for a region never loaded, `setRegion` leaves the page where it was with the needs-a-signal line.
- [ ] **Step 6: Bump `BUILD` if `map3d.js` changed, commit** (`snow: the page loads one region's forecast at a time and tells every time in the mountain's own time zone`).

---

### Task 5: A region with nothing but a forecast still works

**Files:**
- Modify: `snow/map3d.js` (`region.lake` optional), `snow/index.html` (`REGIONS` fields optional; `railReady`; `loadRoads`; the region menu)

**Interfaces:**
- Produces: in the page's `REGIONS` table only `name`, `terrain`, `roads`, `center`, `waterM`, `pick` and `avalanche` are required. `lake`, `chainFeeds`, `closureFeeds`, `short`, `look`, `discKm`, `zoom`, `turnDeg`, `land`, `rev` are optional. `avalanche` may be an empty array.

- [ ] **Step 1: `map3d.js`**: no lake label when `region.lake` is absent.
- [ ] **Step 2: Roads.** A region with no `chainFeeds` hides the Roads button and its note, and `railReady` must not wait for it (today it requires `!$("roadPill").hidden`). The Labels, Shields and Radar buttons close up with no gap.
- [ ] **Step 3: Avalanche.** A region with `avalanche: []` hides the Avalanche map button; the Avalanche tab says in one sentence that no center forecasts this area.
- [ ] **Step 4: The region menu (D7).** With more than three regions the wide layout hides `#regionBar`'s row of names and shows the same chooser the phone uses.
- [ ] **Step 5: Prove it with a throwaway region.** In a temporary copy of the page (`snow/_bare.html`, not committed), add a `REGIONS` entry `bare` that reuses Tahoe's terrain with no lake, no feeds and `avalanche: []`, and a `data/forecast/bare.json` made by copying two Tahoe mountains with `region: "bare"`. Check at 393x852: the opening screen lifts within its normal time, the map builds, the button block appears, the Mountain tab shows the "no lift feed" state it shows for a backcountry spot, no console errors. Delete both files.
- [ ] **Step 6: Commit** (`snow: a region can have no lake, road feeds or avalanche center and the map still comes up whole`).

---

### Task 6: Favorites

**Files:**
- Modify: `snow/index.html`

**Interfaces:**
- Consumes: `index`, `loadRegion`, `setRegion` (Task 4).
- Produces:
  - `prefs.favorites: string[]` (mountain keys, in the order starred) in `turbo-snow.prefs`.
  - `region` may now be `"favorites"`. `place()` returns the real region key: `region === "favorites" ? regionOf(selected mountain) : region`. **Every `REGIONS[region]` and `avy[region]` in the page becomes `REGIONS[place()]` / `avy[place()]`**; `here()` returns the favorites (those whose region is loaded, in saved order) when `region === "favorites"`.
  - `isFavorite(key)`, `toggleFavorite(key)`.

- [ ] **Step 1: The star.** The existing star button (`button[data-home]`) becomes `aria-pressed` toggle of `toggleFavorite`; the `homeAsk` dialog and its handlers go. `homeOf(key)` returns the first favorite in that region, else `REGIONS[key].pick`. One-time migration on load: each saved `tahoe-snow.home.<region>` (and the bare `tahoe-snow.home` for Tahoe) is appended to `prefs.favorites` if absent, then the old keys are removed. Pressing the star dips and holds like every other button; no colour flash.
- [ ] **Step 2: The menu.** "Favorites" is the first option of `#regionPick` and `#sumPick` when `prefs.favorites` has at least one key the index knows. The title beside the pin reads "Favorites".
- [ ] **Step 3: Choosing it.** `setRegion("favorites")` loads every region that holds a favorite (`Promise.all` of `loadRegion`), then renders. The Region tab lists the favorites in saved order, each row carrying its region's short name where today's rows carry nothing. `selected` becomes the first favorite.
- [ ] **Step 4: The map, roads and avalanche follow the selected mountain.** When `selected` changes and `place()` changes with it, do what `setRegion` does for a real region today (`loadAvalanche(); startMap();`). Within one place, selecting another favorite only moves the map as it does now.
- [ ] **Step 5: Edge cases (Review Focus 3).** A favorite the index does not know is ignored and kept. Removing the last favorite while on Favorites returns to the place on screen. A favorite whose region file fails to load is left out of the list with the others shown.
- [ ] **Step 6: Check in the preview** at 393x852, light and dark: star two Tahoe mountains and one Eastern Sierra mountain; Favorites appears; the list shows three; tapping the Eastern Sierra one rebuilds the map there and the Avalanche tab shows ESAC; reload keeps it; unstar all three and the menu entry goes. Set `localStorage["tahoe-snow.home.tahoe"]="kirkwood"` with no prefs, reload: Kirkwood is a favorite and the old key is gone.
- [ ] **Step 7: Commit** (`snow: any mountain can be starred, and Favorites lists the starred ones from every region; the star no longer asks first`).

---

### Task 7: The first new region, end to end (Salt Lake)

**Files:** as `snow/docs/adding-a-region.md` lists.

- [ ] **Step 1: Follow `adding-a-region.md` for `saltlake`** with the mountains in the design's starting list. It is two pushes: the configuration first (so the collector builds real data), the page second (against that data).
- [ ] **Step 2: Correct the guide** wherever a step was wrong, unclear or missing. The guide is the deliverable of this task as much as the region is.
- [ ] **Step 3: Add the two known weaknesses to the About sheet** (design, "What each new region gets"), as two plain sentences where the snow-density model is described.
- [ ] **Step 4: Commit** each push as the guide says.

### Task 8: The remaining regions

- [ ] `seattle`, `tetons`, `newengland`, `alaska`: one pass of the guide each, one region per session, in that order. After each, `python -m pytest -q` proves the allowance still fits, and the next morning's ledger (`archive/usage.json` on `snow-data`) confirms it: `calls_24h` under 8,500 and `rate_limited` 0.

### Task 9: Retire the single file (two weeks after Task 4 ships)

- [ ] Remove the `forecast.json` merge from `pipeline.run`, the fallback from the page's loader, and the file from the collector's publish. Commit (`snow: the single forecast file is gone; every copy of the page reads the regions' own files`).
