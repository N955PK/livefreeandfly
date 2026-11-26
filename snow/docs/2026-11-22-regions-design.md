# More regions and Favorites: design

Written 2026-11-22. This is the spec. The work is in `2026-11-22-regions-plan.md`, and the repeatable steps for
each new region are in `adding-a-region.md`.

## What is being built

1. Turbo Snow covers more regions than Tahoe and the Eastern Sierra: Seattle, Salt Lake, the Tetons, New England
   and Alaska to start, with room for a few more.
2. A **Favorites** list that holds mountains from any region and is chosen from the same menu as a region.

## What limits it: the forecast allowance

Every forecast comes from Open-Meteo's free service. Its limits (per IP address, read from their terms 2026-11-19,
held in `tahoe_snow/sources/openmeteo.py`):

| Limit | Calls |
|---|---|
| per minute | 600 |
| per hour | 5,000 |
| per day | 10,000 |
| per month | 300,000 (the same as 10,000 a day) |

A "call" is not a request. A request is charged `variables x models / 10` (at least 1) times `days / 14` (at least 1).
One mountain, one forecast run, measured from the ledger (`archive/usage.json`, 21 mountains = 1,089.0 calls):

| Request | Why | Calls |
|---|---|---|
| 4 models x 37 variables, 14 days ahead + 8 back | the forecast itself, with the air aloft for snow density | 23.3 |
| GFS ensemble, 31 members x 2 variables | the range | 6.2 |
| ECMWF ensemble, 51 members | the range | 10.2 |
| ICON ensemble, 40 members | the range | 8.0 |
| GEM ensemble, 21 members | the range | 4.2 |
| **One mountain, one run** | | **51.9** |

So the whole budget is one sum: **mountains x runs a day x 51.9 must stay under 8,500** (85% of the day; the run's
own check complains at 90%, and a retry after a failure needs room).

### What that supports

| Plan | Mountains in all | New ones |
|---|---|---|
| Everything 4 times a day (as now) | 40 | 19 |
| **Tahoe and Eastern Sierra 4 times a day, new regions twice (recommended)** | **60** | **39** |
| Same, and new regions' ranges ignore each member's temperature | 76 | 55 |
| Tahoe and Eastern Sierra 4 times, new regions once a day | 100 | 79 |

The recommended plan: the 21 home mountains keep a forecast every 6 hours (4,356 calls a day). New regions get one
every 12 hours, 103.7 calls a mountain a day. The weather models behind the forecast update every 6 to 12 hours, so
twice a day loses little.

The third row is not recommended to begin with. Dropping the members' temperature makes the range blind to an
uncertain rain line, which is exactly what matters in Seattle and New England.

Other ways to make room, in the order to reach for them:
- **Ask for one past day instead of eight** and keep the earlier days from the previous run. Saves 7.4 calls a run
  (14%). More code, no loss of quality.
- **Pay Open-Meteo.** Their paid plan is about $30 a month for 1,000,000 calls a month (check the current price):
  three times the free allowance, roughly 250 mountains at the recommended pace.

Favorites cost nothing. A forecast is built for every mountain in the list whether or not anyone stars it. There
is no way to build a forecast only when someone asks: the page has no server.

### The starting list (30 new mountains, 7,470 calls a day, 75% of the allowance)

| Region (key) | Mountains | Time zone | Avalanche center |
|---|---|---|---|
| Seattle (`seattle`) | Crystal Mountain, Stevens Pass, Summit at Snoqualmie, Alpental, Mt. Baker, White Pass, Mission Ridge | America/Los_Angeles | NWAC |
| Salt Lake (`saltlake`) | Alta, Snowbird, Brighton, Solitude, Park City, Deer Valley, Snowbasin, Powder Mountain | America/Denver | UAC |
| Tetons (`tetons`) | Jackson Hole, Grand Targhee, Snow King, Teton Pass (backcountry) | America/Denver | BTAC |
| New England (`newengland`) | Stowe, Jay Peak, Sugarbush, Killington, Cannon, Sunday River, Sugarloaf, Tuckerman Ravine (backcountry) | America/New_York | MWAC |
| Alaska (`alaska`) | Alyeska, Turnagain Pass (backcountry), Hatcher Pass (backcountry) | America/Anchorage | CNFAIC, HPAC |

That leaves room for about ten more mountains at twice a day: one more region (Colorado's Front Range, say), or a
few additions to these. Juneau (Eaglecrest) is too far from Anchorage to share a map and would be its own region.

All five avalanche centers answer on the same public service the page already reads (`api.avalanche.org`, checked
2026-11-22: NWAC 10 zones, UAC 9, BTAC 4, MWAC 1, CNFAIC 4, HPAC 1).

## What each new region gets, and what it does not

| Part of the app | New regions at launch |
|---|---|
| Forecast, range, hourly chart, powder days | Yes, same method |
| 3D map with the mountains on it | Yes; terrain and road lines are built once per region |
| Avalanche forecast, photos, offline copy | Yes |
| Measured snow and season totals | Where a SNOTEL sensor is near (Washington, Utah, Wyoming, Alaska). New England has none: those mountains read "Uncorrected" and show no measured snow, as June Mountain does now |
| Forecast corrected against the sensor | No. A correction has to be fitted per region from years of sensor record (`calibrate.py`). Until then the models are used as they are |
| Lift and trail status, resort report | Not at launch. Each resort's feed has to be found and wired one at a time; the guide says how |
| Road and chain status | No. That comes from Caltrans only |
| Wind-hold outlook | Uses the default tier until holds are logged |

Two known weaknesses to say plainly on the About sheet when the regions ship:
- The snow-density model was trained on Sierra snow. It reads the air aloft, so it will follow colder storms, but it
  has never been checked against Utah or Teton powder and probably under-reads it.
- The weights that blend the four models were fitted in the Sierra.

## Decisions

**D1. One forecast file per region.** Today the page downloads one 3.1 MB file for 21 mountains (about 150 KB a
mountain). At 60 mountains that is 9 MB on every open. The data branch will hold `forecast/<region>.json` (the same
shape as today's file, that region's mountains only) and a small `index.json` listing every mountain. The page
loads the index, then only the region on screen. `forecast.json` keeps being written with Tahoe and the Eastern
Sierra until installed copies of the old page have gone (remove it two weeks after shipping).

**D2. One region per collector pass.** Each region has its own interval (6 or 12 hours). On each pass the collector
builds the one region that is most overdue, if any is. A region is at most 8 mountains: about 80 seconds and 415
calls. That keeps lift status flowing, and stays far under the hourly limit, which a 60-mountain run in one go
(3,100 calls) would crowd.

**D3. Each region has its own time zone.** Days, "overnight", lift hours and every clock on a chart are told in the
mountain's own time. Today `America/Los_Angeles` is a constant in `pipeline.py`, `blend.py` and about twenty places
in `index.html`. It becomes a field of the region, published with each mountain as `tz`.

**D4. The region table lives in `config.py`.** One `Region` per region: name, time zone, interval, avalanche
centers. The avalanche bundle and the collector read their center lists from it. A test adds up the configured
mountains and fails if they would spend more than 8,500 calls a day, so nobody can add a region past the allowance
by accident.

**D5. Favorites replaces "home mountain".** Today each region has one starred home mountain, set through a
confirmation dialog. The star becomes a plain toggle: any number of mountains, any region, no dialog. A region
opens on its first favorite, or its default if it has none. Saved home mountains become the first favorites.
Favorites are kept on the device (`turbo-snow.prefs`), as every other choice is.

**D6. Favorites is a list, not a place.** The region menu gains "Favorites" at the top when there is at least one.
It changes which mountains the Region tab lists. The map, roads and avalanche tabs need a real place, so they
follow the region of the selected mountain: pick a Utah favorite and the map is Utah's. Opening on Favorites loads
only the regions that hold a favorite.

**D7. The region menu is a menu everywhere.** The wide-screen row of region names ("Tahoe / Eastern Sierra") does
not fit seven names. With more than three regions the wide layout uses the same menu as the phone.

## Out of scope

Lift feeds, road status and fitted corrections for the new regions; a region outside North America (the models are
global, but the avalanche and sensor sources are not); sharing favorites between devices.
