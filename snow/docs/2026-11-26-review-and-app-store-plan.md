# Turbo Snow: review and App Store plan (2026-11-26)

Three independent reviews were run on this date: the front end, the data side, and App Store readiness. This
document records what they found, what was fixed the same day, and a plan for a store release. Findings marked
"read" come from reading the code; "seen" were reproduced in a browser; "unconfirmed" could not be checked.

## Where it stands

The forecast and its testing are the strong part: 337 mountains in 46 regions, corrections fitted and tested region
by region, and the app says plainly where nothing is fitted. The lift readers are careful: most check the page's own
counts and refuse a page they do not recognise.

It is not yet a product. It runs on free tiers used past their terms, nobody is told when something breaks, every
push goes straight to users with no test run, and parts of the data may not be used in a store app without
permission. None of that shows on screen, which is why it needs saying.

## Fixed during the review

- A request to GitHub with no time limit could leave the app on "Loading the forecast…" indefinitely (seen). It
  now has a deadline of its own.
- The page read developer file paths whenever its hostname was `localhost`, which is how app wrappers serve a
  page. It now does so only when served from a port.
- Every new version of the page made each phone download all the maps again, about 27 MB. Maps are now kept in a
  store of their own and only missing ones are fetched.
- An update on a weak signal could leave the phone with less saved than before. Files that fail to download are
  now carried over from the previous version.
- Six regions' maps were never saved for offline, and two were saved under the wrong address. The list is now
  generated from the page's regions and checked by a test.
- The credits were missing Avalanche Canada, British Columbia's licence statement, the terrain data's credits and
  OpenStreetMap's wording. All are now named.
- Header text ran into the elevations on 315 mountains at 360 px wide. Measured on all 337 mountains at four
  widths; clean at 393, 375 and 360 px.

## Open defects, in order

### Must fix before any store release

1. **No test gate.** Nothing runs the tests before a push reaches users. Three broken commits went out on the
   day of this review. Add a workflow that runs the tests on every push and deploy only when it passes.
2. **No alerting.** Collector failures are logged as warnings and the job ends green. Add a heartbeat: a check that
   fails loudly when a region's forecast is more than a few hours late.
3. **One failing region can starve its collector** (read). The most overdue region is always tried first, so one
   that keeps failing is retried every half hour and spends calls each time. Back off after a failure.
4. **A failed lift reader makes its mountain's status vanish.** Keep the last good reading with its time.
5. **First launch with no signal** shows only "The forecast could not be loaded", with no reason and no retry
   (seen).
6. **"Offline." is shown for any failure**, including a server error while online, and never clears (read).
7. **GitHub's limit of 60 unauthenticated calls an hour per address**; each launch uses five (seen). On shared
   lodge Wi-Fi it runs out. Stop asking the API from the page: publish a small pointer file instead.

### Should fix

8. **Speed.** With the processor slowed four times, a tap on a mountain took 1.6 s and a region change 2.6 s
   (seen). Most of it is thousands of time-zone formatting calls per draw, and redrawing everything on each tap.
9. **Every visit downloads every region's forecast**, about 5 MB compressed (estimated). Load on demand.
10. **Accessibility.** Summary rows cannot be reached by keyboard; dialogs have no accessible names; grey text is
    3.1:1 against a 4.5:1 standard; several touch targets are under 44 px (search 30, region pin 25 wide); all
    type is in pixels. An app is held to this more than a web page.
11. **Copy.** The two About pages still use "standard deviation", "ensemble members", "wet-bulb" and "held out".
    In metric the grid still says "6 in or more". Avalanche zones can be named "Colorado 1".
12. **three.js comes from a public CDN**; when it fails the map disappears without a word. Bundle it.
13. **Hand-kept tables.** Lift feeds are listed twice by hand (165 keys each) and place names are split across
    three tables. They agree today; a test should keep them agreeing.

### Honest limits to state, not fix

- 39 of 337 mountains have a sensor-corrected forecast. 59 share a neighbour's weather point.
- Several lift readers have only seen closed, pre-season pages.
- Nothing has been checked on a real phone, in Safari, or with VoiceOver.

## What a store release changes

| Matter | Finding | Confidence |
|---|---|---|
| Open-Meteo | The free tier is non-commercial; five collectors together plan about 42,800 calls a day against one 10,000 allowance. Paid plans are $29 a month (1 million calls) and $99 a month (5 million). | Medium: prices from its blog, terms page not read |
| Lift status | Alterra's terms bar scraping. Apple's guideline 5.2.2 requires that third-party content be "specifically permitted" and may ask for proof. The Vail reader imitates a browser to pass bot checks. | Medium |
| Avalanche | The US centers' API sets display rules the app already follows, but states no licence for the danger icons. Avalanche Canada's terms require written consent. | Medium (US), low (Canada) |
| Guideline 4.2 | An app must be more than a repackaged website. A bare wrapper is the likeliest rejection. | High on the text |
| Government data | SNOTEL, NOAA and the like are public domain; British Columbia's needs its licence statement. | Medium-high |
| OpenStreetMap, terrain | Usable with the attribution now in the credits. | High |
| The fifty classics | Names and facts are not protected; listing them with credit is low risk. | Medium |
| Resort and pass names | Plain-text labels are fair; no logos, and keep them out of the app's name and keywords. | Medium-high |

## The plan

### Phase 0: decide (a week, no code)

Three decisions shape everything after:

- **Free or paid.** Free keeps the Open-Meteo question open but does not settle it: a store app is arguably
  commercial either way. Recommended: plan for the $99 plan, and cut calls first so $29 may do.
- **Lift status.** Launch without it, link out to each resort, or license a feed. Recommended: launch with the
  forecast, sensors and avalanche summaries, keep lift status for resorts that agree in writing, and link out for
  the rest. Ask OnTheSnow and SnoCountry for prices in parallel.
- **Wrapper or native.** Recommended: wrap the existing page with Capacitor for the first release, with the
  page and maps bundled in the app and two native features, then judge whether a SwiftUI rewrite is worth it.

Send three letters now, because replies take weeks: Open-Meteo (commercial terms for this use), the National
Avalanche Center (icons and API in an app), Avalanche Canada (written permission).

### Phase 1: make it a service (3 to 4 weeks)

- A test workflow and gated deploys. Staging and production as separate branches.
- One paid Open-Meteo key and one collector, in place of five free allowances. Cut calls: share weather points
  further, and build remote single-mountain regions twice a day.
- Move the collectors off Actions to a small always-on machine or scheduled cloud jobs, and the published files
  to object storage behind a CDN. Rough cost: $10 to $30 a month.
- Alerting: a heartbeat per collector and per region, sent to a phone.
- Last-good lift status; back-off for failing regions; a contract test for the published JSON's shape.

### Phase 2: make it an app (4 to 6 weeks)

- Capacitor shell with the page, three.js and the maps bundled. Works offline from the first launch with the
  last forecast.
- Two native features that a website cannot have, which is what guideline 4.2 turns on: **powder alerts** by
  push for favourite mountains, and a **home-screen widget** with a favourite's next three days. Both need a small
  Swift target. Alerts need somewhere to keep device tokens, which ends "no data collected": say so in the
  privacy label.
- The speed and accessibility items above. Type that scales, 44 px targets, VoiceOver labels.
- A safety statement shown once and kept in About: forecasts are estimates, and avalanche summaries point to the
  centers' forecasts and do not replace them.

### Phase 3: submit (2 weeks)

- Apple Developer Program, $99 a year. Builds need Xcode 26 on a recent Mac, or a cloud build service.
- Privacy policy and support pages; privacy label; age rating; export compliance (exempt: HTTPS only).
- Screenshots, a name and subtitle with no resort or pass marks, "not affiliated" in the description.
- TestFlight with ten to twenty skiers for two storms before submitting.
- Keep written permissions on file; Apple can ask for them.

### Phase 4: after launch

- Android from the same Capacitor project.
- Grade live forecasts against the sensors by lead day and show the result; it is the app's real difference from
  the others.
- Decide on price once there is a season of use. OpenSnow charges roughly $35 to $50 a year (unconfirmed);
  Slopes about $30. A free forecast with an optional subscription for alerts and widgets would sit below both.

## Rough cost to run

| Item | Monthly |
|---|---|
| Open-Meteo | $29 to $99 |
| Hosting, storage, CDN | $10 to $30 |
| Apple Developer Program | about $8 ($99 a year) |
| Licensed lift feed, if taken | unknown; ask |

## Not established

- Open-Meteo's and GitHub's current terms were not read directly.
- Whether the collector starvation has ever happened.
- How the service worker behaves live; the test harness blocks it.
- Anything on a real iPhone.
