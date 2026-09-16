# N955PK / acroReplay — real-time aerobatic figure replay

A live 3D recreation of the aircraft, driven by the OnFlight Hub's real-time data
stream, so the pilot can review each aerobatic figure immediately after flying it
and iterate on corrections during the repositioning leg — instead of waiting for a
post-flight ACROWRX upload.

This document is the working plan. It is written to be resumable: every open
unknown is listed with the branches we expect and what to do in each branch, so
work can restart the day the Hub is on the bench.

---

## 1. Mission and scope

**The loop we are building:** fly a figure → the system detects the figure ended →
the kneeboard tablet automatically replays the figure in 3D from the judge's
viewpoint with traces and numbers → pilot adjusts → flies it again. Cycle time
target: replay available within ~2 s of figure end, consumable within the 10–20 s
repositioning leg.

**Explicit non-goals:**

- No ground-coach / remote live view (descoped 2026-08-12 — the pilot in the
  cockpit is the only consumer). This removes all cloud, LTE-relay, and
  long-range-telemetry work.
- No scoring/sharing platform. ACROWRX already does post-flight scoring,
  judging, and social features; this project is the complementary live tool.
  Nothing here requires touching ACROWRX's service.
- No sensor fusion of our own (unless forced into hardware plan C, §4 U3-c).
  The Hub's onboard 50 Hz EKF is the INS.

## 2. System context (research, 2026-08-12)

### 2.1 The ecosystem

- **ACROWRX** (acrowrx.com): Paulo Iscold's post-flight aerobatic analysis
  platform (web app: Next.js/React, Clerk auth, CesiumJS 3D; built largely by
  Christopher Sheehan). Grew out of Iscold's Red Bull Air Race telemetry work.
- **OnFlight Hub** ($599, Bolder Flight Systems / Brian Taylor, ex-NASA): the
  consumer data unit ACROWRX users fly. We own one.
- Iscold's original high-end unit (~$7k, 100 Hz, dual GNSS, control-position
  inputs) exists but is irrelevant to us.

### 2.2 OnFlight Hub internals (from the user manual,
bolderflight.com/assets/onflight/user_manual.pdf)

- **Two processors.** A DAS processor does real-time sensing, state estimation,
  and SD logging. A separate Wi-Fi processor hosts the config website, streams
  GDL90, broadcasts "a more complete set of data over UDP at a higher rate…
  enables developers to create applications using this real-time data," and
  accepts external sensor modules (Stadia lidar AGL, BLE heart rate).
- **Estimation.** IMU + magnetometer + GNSS + static pressure fused at 50 Hz by
  an EKF. IMU data-ready interrupt triggers each 50 Hz frame. Tilt-compass
  initialization; gyro biases estimated during the first ~5 s stationary;
  in-flight bias states in the EKF. Mag is used only for initialization.
  Both raw and processed values go to the data log.
- **INS initialization requires a 3D GNSS fix** (min satellites, and min
  accuracy on FW v8+). Status LED: solid = INS healthy; off = no init / poor
  GNSS; fast flash = healthy but no SD card.
- **Config page at `192.168.23.1`** on the Hub's open Wi-Fi AP (SSID
  "OnFlight Hub" + serial on FW v6+). Page shows live values (so a live data
  path to the browser already exists — see U4). Config includes: GDL90 port,
  datalog rate (50/25/10/5 Hz — *the EKF always runs at 50 Hz*), mounting
  rotation matrix, IMU bandwidth, accel/mag bias + scale-factor matrices, GNSS
  nav rate (1/5/10 Hz) and min satellites, and the **ACROWRX key** field, which
  switches log output to the ACROWRX format.
- **GDL90:** heartbeat + ForeFlight ID at 1 Hz; ownship position, GNSS
  altitude, and attitude at 5 Hz.
- **Reference frame:** right-handed, x out the nose, y right wing, z down
  (NED-style body frame), with a configurable 3×3 rotation to the aircraft
  frame.
- **Specs:** ±16 g, ±2000 °/s, 0–650 kt, −10k…+55k ft, 13 h battery, USB-C,
  microSD, 4×2.75×1 in, 5 oz.
- **Data converter** (desktop app) exports logs to CSV and MATLAB; AviNet,
  FlySto, CloudAhoy, ACROWRX read the native format.

### 2.3 Relevant open source

- **github.com/bolderflight** (MIT/BSD, C++, Teensy-oriented): `navigation`
  (15-state GNSS-aided EKF INS + tilt compass + all frame transforms — very
  likely the algorithm inside the Hub), `framing` (start byte / end byte /
  checksum packet framing — likely the UDP wire framing), `mavlink`, `leb128`,
  `invensense-imu`, `bmi088`, `ublox`, `airdata`, `wmm`, `filter`, `mat_v4`
  (MATLAB v4 log writer — tells us the .mat export layout).
- **GDL90 parsers:** NathanVaughn/gdl90py, etdey/gdl90, balfieri/gdl90.
  ForeFlight extended spec: foreflight.com/connect/spec — UDP to port 4000 on
  the display device, unicast strongly preferred, discovery via JSON broadcast
  from the app on port 63093, AHRS msg 0x65 (roll/pitch/heading 0.1°, IAS/TAS)
  at 5 Hz. **5 Hz attitude is unusable for aerobatics** (~80° of roll between
  samples at competition roll rates) — GDL90 is a bring-up fallback only.
- **OpenAero** (github.com/OpenAero/main, GPL, JS): Aresti/OLAN sequence
  parser/renderer — future intended-vs-flown overlays. GPL: keep isolated as a
  separate module/service, or accept GPL for the whole app.
- **X-Plane UDP data output**: Settings → Data Output streams selected
  datasets (attitude, position, rates) over UDP at configurable rates — the
  dev-time stand-in for the Hub.

## 3. Target architecture

```
OnFlight Hub ──Wi-Fi UDP 50 Hz──► bridge (Python asyncio) ──WebSocket──► browser (three.js)
X-Plane UDP ─────dev-time────────►   • source adapters                     • live 3D scene
log replay ──────dev-time────────►   • ring buffer (~10 min)               • HUD instruments
                                     • figure segmenter                    • auto replay UI
                                     • parquet session log
```

### 3.1 The internal contract: `StateSample`

Everything upstream of the renderer normalizes to one dataclass. Whatever the
UDP payload turns out to be, only the OnFlight adapter changes.

| field        | type/units                                | notes                                  |
|--------------|-------------------------------------------|----------------------------------------|
| `t`          | float s, monotonic stream time             | from packet counter/timestamp if present, else arrival time |
| `t_utc`      | float s (unix) or None                     | from GNSS time if present              |
| `lat, lon`   | deg (WGS-84)                               |                                        |
| `alt_msl`    | m                                          | INS altitude                           |
| `ned_pos`    | (3,) m, relative to session origin         | computed in bridge from lat/lon/alt    |
| `ned_vel`    | (3,) m/s                                   |                                        |
| `quat`       | (w,x,y,z), body(FRD)→NED                   | if stream gives Euler, convert in adapter; never store Euler internally |
| `body_rates` | (3,) rad/s (p,q,r)                         |                                        |
| `body_accel` | (3,) m/s² specific force                   |                                        |
| `load_factor`| g, positive up                             | Hub computes this post-EKF, low-passed |
| `pressure_alt`| m or None                                 |                                        |
| `gnss`       | dict: fix, sats, hacc, vacc (if available) | drives a data-quality badge in the UI  |
| `quality`    | enum: OK / DEGRADED / STALE                | set by adapter (INS health, gaps)      |

Frames and conventions: body = front-right-down; local frame = NED with origin
fixed at first-valid-fix (renderer converts NED→three.js Y-up: x_east→x,
−z_down→y, x_north→−z or similar — write the mapping ONCE in a tested module;
this bit BayRadar repeatedly).

### 3.2 Bridge (Python 3.11, asyncio, stdlib + websockets + numpy + pyarrow)

- `sources/` package, one adapter per input, each an
  `async def stream() -> AsyncIterator[StateSample]`:
  `onflight_udp.py` (primary, blocked on U1/U2), `gdl90.py` (fallback,
  gdl90py), `xplane_udp.py` (dev), `log_replay.py` (dev; plays converter CSV /
  ACROWRX files at wall-clock or Nx speed).
- Fan-out hub: latest-sample WebSocket broadcast (JSON for MVP; msgpack or a
  packed binary frame if profiling ever says so — at 50 Hz × ~40 floats it
  won't).
- Ring buffer: deque of ~10 min × 50 Hz samples; replay endpoint serves
  arbitrary [t0, t1] slices.
- Session log: parquet append (one file per power-on session).
- Figure segmenter (phase 3) runs in the bridge, not the browser, so replay
  triggers and future audio cues share one implementation.

### 3.3 Frontend (three.js, plain Vite + TS; no React needed at this scope)

- Local ENU scene: 1000 m aerobatic box (white corner/edge markers per IAC
  practice), ground grid, horizon/sky dome, low-poly aerobatic aircraft model.
- Attitude via quaternion slerp over an interpolation buffer of 2–3 samples
  (40–60 ms) → 60–120 fps render from 50 Hz data; dead-reckon with body rates
  when a gap exceeds one sample interval; show STALE badge past 250 ms.
- Ribbon trail (colored by g or roll rate — the teaching signal) + optional
  wingtip smoke trails.
- Cameras: judge position (default — ground-level at box center-front), free
  orbit, chase.
- HUD overlay (SVG/canvas, not in-scene): g, roll rate, alt/speed tapes, GNSS
  quality badge.
- Replay mode: auto-triggered by segmenter event over WebSocket; scrub bar,
  0.25–1× speed, per-figure annotations later.
- Kneeboard constraints from day one: huge tap targets, high-contrast sunlight
  palette, no hover-only affordances.

## 4. Unknowns and contingency branches

This is the section to reread when the Hub is in hand. U1–U4 all resolve from
one bench capture session (§5).

### U1 — RESOLVED 2026-09-15: always-on UDP **broadcast** to 192.168.23.255

Three broadcast flows, no configuration or discovery handshake needed:
**port 2000 — the INS stream, 67-byte frames at 50 Hz** (median 20.0 ms);
port 4000 — GDL90 (heartbeat + ForeFlight ID at 1 Hz; ownship + geo-alt +
AHRS packed in one datagram at 5 Hz); port 2005 — a 55-byte identity message
at 1 Hz (serial, tail number, pilot name, aircraft type). Broadcast means the
iOS native path needs the multicast entitlement (§7.1) — or a bridge.
*(Original branches kept below for the record.)*

#### U1 — original question: how is the developer UDP stream delivered?

Manual says it exists but not port, addressing, or whether it needs enabling.

- **Expect (most likely):** UDP broadcast to 192.168.23.255 or
  255.255.255.255 on a fixed port, always on. Bolder Flight's other products
  (SPAARO ecosystem) lean simple. → tcpdump sees it immediately; proceed to U2.
- **Branch b — unicast-to-known-client:** the Hub may unicast only to clients
  it discovers (the GDL90 path listens for ForeFlight's JSON discovery
  broadcast on port 63093). → Mimic discovery: broadcast
  `{"App":"acroReplay","GDL90":{"port":4000}}`-style JSON on 63093 and watch
  what arrives; also just run ForeFlight on an iPad on the same network and
  sniff what the Hub sends it (GDL90 at minimum — but check for a second,
  faster flow).
- **Branch c — off until configured:** a setting on the config page (or only
  visible after the ACROWRX key is entered) enables it. → Mirror of the config
  page (capture script step 1) will show the knob; the endpoint probe list
  will show config POST paths.
- **Branch d — nothing found:** email support@bolderflight.com citing the
  manual's developer-UDP paragraph and ask for the spec (their site advertises
  "published protocols"; Brian Taylor open-sources nearly everything — high
  probability of a helpful answer). Meanwhile build against GDL90 5 Hz +
  log replay so the app keeps moving.

### U2 — RESOLVED 2026-09-15: raw packed little-endian struct, no framing

Byte 0 is a message id (0x02 = INS frame on port 2000, 0x00 = identity on
port 2005); no start/stop bytes or checksum (UDP already delimits — the
bolderflight `framing` scheme is not used here), not MAVLink. Field encodings
are exactly the manual's spec-table ranges: int16 ÷100 angles, uint16 ÷100
knots (0–655 kt), uint16 − 10000 ft altitudes (−10,000…55,535 ft), int16 ÷10
ft/min climb (±3,276), int16 ÷10 deg/s rates (covers ±2,000), int16 mg
accelerations (±32 g), int32 ÷1e7 lat/lon, uint32 ms system time. Full layout
in docs/PROTOCOL.md; decoder `onflight/udp_ins.py`; fixtures in
`tests/fixtures/` (location and identity strings scrubbed — public repo).
Every field was confirmed against an independent source: the WebSocket status
frame (pitch/roll/lat/lon/alts/GNSS/UTC/temps), GDL90 (true heading to 0.04°,
track, ground speed, pitch/roll), physics (1 g / 982 mg stationary, rotation-
angle rates vs gyro), and the local magnetic declination (12.54° E) for @21.
*(Original branches kept below for the record.)*

#### U2 — original question: wire format of the stream

- **Branch a — self-describing (JSON/CSV text):** decode trivially. Possible:
  the Wi-Fi processor is a small MCU (ESP32-class) and JSON at 50 Hz is cheap.
- **Branch b — bolderflight/framing binary (likely):** start/end bytes +
  checksum per their `framing` repo; payload almost certainly little-endian
  packed floats/uint in SI units, matching the data-converter CSV channel
  list. → Port framing decode from their C++ (small), then field-map (§6).
- **Branch c — MAVLink:** they maintain a mavlink repo. Check magic byte
  (0xFE v1 / 0xFD v2) → if yes, pymavlink dumps everything, done.
- **Branch d — opaque custom binary:** full correlation methodology (§6). This
  still works — it's just a day of work instead of an hour.

### U3 — RESOLVED 2026-09-15: full INS solution at 50 Hz — sufficient for 3D

The 67-byte frame carries pitch, roll, true heading (+ declination), ground
speed, ground track, flight-path angle, climb rate, load factor, 3-axis body
rates, 3-axis body acceleration, WGS-84 / MSL / cabin-pressure altitude,
static pressure, lat/lon, GNSS fix/sats/accuracies, UTC, health flags (incl.
INS-initialized and INS-healthy bits), and system time. Missing versus the
ideal `StateSample`: NED velocity components (derive from ground speed +
track + climb rate) and a quaternion (build from the Euler triple in the
adapter — 0.01° resolution is fine). Plan C is closed.
*(Original branches kept below for the record.)*

#### U3 — original question: stream content and rate

- **Expect:** full INS solution (attitude, position, velocities, rates,
  accels, load factor, pressure alt, GNSS status) at 50 Hz — i.e. a superset
  of the log record. Verify: packet interval histogram ≈ 20 ms; payload size
  constant.
- **Branch b — slower or partial (e.g. 10 Hz, or position-only):** 10+ Hz with
  attitude is still usable (slerp hides more); position-only is not. →
  Escalate to Bolder Flight (rate knob? firmware roadmap?), fall back to GDL90
  for dev, and open **plan C:** custom Teensy 4.x + BMI088 + uBlox + BMP390 +
  ESP32 unit built on their own `navigation` EKF (~$150 parts) — we own the
  stream then. Plan C is a last resort; do not start it before U1–U3 resolve.
- **Branch c — stream is ACROWRX-proprietary after key entry:** capture both
  with and without the key entered (§5 step 7) and diff. If the no-key stream
  is sufficient, use it and avoid the encumbered format entirely.

### U4 — RESOLVED 2026-09-15: the Hub serves `ws://192.168.23.1/data` (binary)

The mirrored page JS opens a WebSocket that pushes a **101-byte little-endian
status struct** — full layout and the HTTP config API (`/config`,
`/sys-config`, `/sensor-config`, `/ins-config`, `/acrowrx`, …) are in
[docs/PROTOCOL.md](docs/PROTOCOL.md); decoder in `onflight/ws_data.py`.
Contents: 4 status-flag bytes, sensor die temps, GNSS fix/sats/accuracies,
UTC, **pitch and roll (0.01°)**, WGS-84/MSL/cabin-pressure altitudes,
external air-data fields, AGL, **lat/lon (1e-7°)**, sys time (ms), heart
rate, 4 analog inputs. Push rate: measured by capture v2.

**Verdict:** it carries no heading, body rates, accelerations, load factor,
or velocities, so it cannot drive the 3D replay — it is a health/GNSS-quality
side channel (and the config API is how we'd read firmware version, mounting
rotation, and the ACROWRX product flag). Its packed-struct style is a strong
hint that the developer UDP stream is also a packed LE struct, most likely
the datalog record. **U1/U2 remain open**: the 2026-09-15 pcaps were empty
because macOS dropped the Hub Wi-Fi mid-capture (competing auto-join
networks) and the Hub's server hangs on unknown URLs — both fixed in the
capture v2 protocol (§5).

### U5 — GNSS indoors: the INS may never initialize on the bench

No 3D fix → no INS init → attitude/position outputs may be absent, flagged, or
garbage, and conceivably the stream doesn't start at all.

- **Protocol answer:** run the capture session outdoors or at a window with
  sky view; confirm the status LED is SOLID before starting phases; the
  config page header shows fix type and satellite count — the script captures
  it. If stuck indoors: still capture (raw-sensor channels and framing are
  learnable without a fix) but expect to repeat outdoors.

### U6 — ACROWRX key state

The key changes the SD log format; unknown whether it also alters the UDP
stream or unlocks features. → Record current key state during capture; if a
key is available, do a second short capture after entering it and diff
(§5 step 7). Keep pcaps from both modes in the repo.

### U7 — GDL90 port default

Manual screenshot shows `GDL90-Port: 0` (possibly "disabled until set" on
older firmware) while ForeFlight expects 4000. → If no GDL90 seen in pcap, set
port to 4000 on the config page and re-capture. Low stakes (GDL90 is fallback
only) but cheap to check.

### U8 — Firmware version spread

Features are firmware-gated (meta data + log rate v6+, accuracy gates v8+,
SSID suffix v6+). → The config page shows the version; the capture records it.
If old firmware, check bolderflight.com for an updater before concluding a
feature is absent. Do NOT update firmware mid-investigation without a capture
of the current behavior first.

## 5. Bench session protocol (run when the Hub is in hand)

Time: ~20 min. Needs: Hub charged, outdoor spot or big window, this repo on
the Mac, `sudo` password.

1. Power the Hub on a stable surface; don't move it for 10 s (gyro-bias
   init). Wait for the status LED to go solid (INS initialized — needs GNSS).
2. Start `python3 capture_onflight.py` from any network — v2 joins the Hub
   SSID itself (`OnFlight Hub 4496A6FE8CE0`, open network) and re-asserts it
   before every step, because macOS otherwise auto-joins a known network with
   internet mid-run. **The Mac is offline from here** — Claude can't help
   live; the script is self-guiding. It will:
   - mirror the config page and GET the four JSON config endpoints (firmware
     version, mounting rotation, ACROWRX flag, datalog format/divider);
   - phase 1 "stationary" (60 s, Hub perfectly still) and phase 2 "moving"
     (60 s, slow hand rotations — ~20 s each of roll, pitch, yaw, one axis at
     a time), each recording simultaneously: ALL traffic on the interface
     (tcpdump), the `ws://hub/data` frames, and any datagrams arriving on
     UDP 4000 while broadcasting ForeFlight's discovery JSON on UDP 63093 (so
     a Hub that unicasts to discovered EFBs starts sending to this Mac).
   Only known URLs are touched — the Hub's web server hangs on unknown paths.
4. Note (photo is fine) the config page header: firmware version, serial,
   GNSS fix/sats, and whether an ACROWRX key is entered.
5. If an SD card is in the Hub: afterwards, copy the RAW log files for this
   power-on session into `sample_logs/` unmodified, and (if the converter app
   is installed) also export CSV + MATLAB versions. A simultaneous SD log +
   UDP pcap of the same minutes is the Rosetta stone for U2 field mapping.
6. Optional (U1 branch b): while still connected, run ForeFlight on an iPad
   on the Hub network — the pcap then also captures whatever the Hub sends a
   real EFB client.
7. Optional (U6): if an ACROWRX key exists, enter it, rerun a single 60 s
   stationary capture, remove key if desired.
8. Reconnect to normal Wi-Fi and hand Claude `captures/<timestamp>/`.

## 6. Decode methodology (Claude's job, post-capture)

1. Parse pcaps with a small pure-python pcap reader (no scapy dependency).
   Cluster packets by (src, dst, port, length). Interval histogram per flow →
   the 50 Hz flow identifies itself. Separate GDL90 (0x7E flag bytes, known
   spec) from the developer flow.
2. Framing: check first bytes across packets. Test against
   bolderflight/framing (header/footer/checksum — verify checksum candidates:
   CRC16/XOR/Fletcher over payload). Test MAVLink magics. Constant-offset
   counter fields reveal themselves by +1/frame deltas.
3. Field mapping, stationary pcap: known truths — rates ≈ 0, specific force ≈
   (0,0,−9.81)±mounting, load factor ≈ 1.00, lat/lon = capture site, MSL alt
   known, pressure alt ≈ known, GNSS sats plausible small int, temperature
   20–40 °C. Scan the payload interpreting every 4-byte (and 8-byte) window as
   LE float/double; windows matching known truths with low variance = candidate
   fields.
4. Field mapping, moving pcap: roll-only motion isolates roll angle + p;
   same for pitch/q and yaw(heading)/r. Attitude channels swing ±large while
   position stays near-constant → unambiguous assignment, including sign
   conventions vs the manual's FRD frame.
5. Cross-check every mapped field against the simultaneous SD-log CSV export
   (channel names + values, time-aligned) if step 5 of §5 produced one.
6. Deliverables: `docs/PROTOCOL.md` (wire format writeup), 
   `bridge/sources/onflight_udp.py` (adapter), pytest fixtures built from pcap
   slices committed under `tests/fixtures/` so the parser is regression-locked.

## 7. Build phases

**Phase 0 — decode. DONE 2026-09-15** (two bench sessions, ~5 min of data).
Exit met: docs/PROTOCOL.md documents the UDP INS frame, identity message,
WebSocket status frame, and HTTP config API; `onflight/udp_ins.py` and
`onflight/ws_data.py` decode them, locked by real-frame fixtures in `tests/`.
Still unverified in flight: GNSS-denied behavior, and how the INS-healthy bit
behaves under sustained high rates (it dropped ~5% of frames during hand
flips on the bench).

**Phase 1 — pipeline skeleton. FIRST CUT DONE 2026-09-16.** `run_bridge.py`
(aiohttp) takes the Hub's live UDP broadcast or a recorded `.bin`/`.pcap`
replayed at wall-clock pace, decodes with `onflight/udp_ins.py`, converts to
three.js world pose in `bridge/frames.py` (tested), fans JSON samples out on
`/ws` at 50 Hz, seeds late joiners with 120 s of history, and logs every raw
frame to `sessions/`. `web/` is a buildless ES-module three.js app (three
vendored — the phone has no internet on the Hub's Wi-Fi): 1000 m box, biplane
model, trail, orbit / judge / chase cameras, 80 ms interpolation buffer, HUD,
LIVE / INS-init / NO-DATA status. Verified in-browser against the recorded
hand-rotation capture. Deviations from the original plan: no Vite/Node
toolchain and no X-Plane source — real recorded frames are the dev feed.
Still to do in this phase: scrub-back UI over the history, and a first live
desk run with the Hub powered.

**Phase 2 — real data.** OnFlight adapter from phase 0 + a data-quality badge.
Exit: live desk demo off the Hub; car-roof drive-around shows sane
position/attitude.

**Phase 3 — the replay loop.** Rule-based segmenter in the bridge: flight-state
machine (IDLE → MANEUVERING → RECOVERY) on thresholds over |p|, |q|, g
deviation from 1, sustained for N frames; figure end = return to near-1g,
low-rate flight for ~3 s. Auto-replay event → frontend plays the segment at
the judge camera. Exit: segmentation F1 ≥ ~0.9 against hand-labeled X-Plane
sessions + acceptable false-trigger rate on a real (non-aerobatic) flight log.

**Phase 4 — flight test.** Kneeboard iPad in an aerobatic aircraft, bridge on
a pocketable host (§7.1). Iterate on sunlight readability, trigger tuning,
replay pacing. Safety note: mount and use must not interfere with egress or
controls; review with the pilot/organizer as appropriate.

**Phase 5 — depth (ordered by value):** per-figure metrics (line angles vs 15°
increments, roll-rate constancy, loop roundness, heading hold on verticals,
box position); Aresti overlay via OpenAero (GPL — isolate); audio cues in the
headset; multi-session comparison ("this loop vs my best loop").

### 7.1 Cockpit display platform: Apple device (decided 2026-08-13; path c chosen 2026-09-16)

**Decision 2026-09-16 — path c, the native thin shell**, over a Pi/ESP32 bridge (extra box in
the plane) and over asking Bolder Flight for a WebSocket (unknown timeline; the Hub firmware
is proprietary even though their libraries are open, and its USB-C port is charge-only, so
self-modifying it is off the table). Implementation in `ios/` (see `ios/README.md`): Swift
listens on UDP 2000 and pushes raw frames into a WKWebView running the unchanged web app,
which now decodes and does frame math in JS (`web/onflight.js`, `web/frames.js`). Blockers
at decision time: Xcode not installed on the dev Mac; multicast entitlement request pending
a paid developer account.

The display is an iPad or iPhone. This is the proven EFB pattern — ForeFlight
plus Sentry/Stratux is exactly "iPad joins a sensor's internet-less Wi-Fi AP" —
and Safari/WebKit runs a three.js scene at native refresh. The iPad mini is
the de-facto aerobatic kneeboard for mass reasons: ~300 g is ~2.4 kg effective
at +8 g; a full-size iPad is ~2×–5× that. iOS tolerates internet-less Wi-Fi
but deprioritizes it: turn off auto-join for other known networks before
flight so the device doesn't wander off the Hub AP.

Browsers cannot receive UDP, so the only question is how samples reach
Safari/the screen. Four paths; which one wins depends on U4 and U1:

| path | needs | notes |
|---|---|---|
| a. Safari → Hub WebSocket directly | U4-a true (Hub serves WS/SSE) | best case: zero extra hardware, pure web app; add to home screen (PWA) for full-screen standalone mode |
| b. Safari → SBC bridge (Pi Zero 2 W joins Hub AP, runs the Python bridge, serves its own AP + web app) | ~$20 SBC on USB power | default if U4-a is false; keeps logging/segmentation without any App Store involvement; AP+STA on one radio needs care (or add a USB Wi-Fi dongle) |
| c. Native thin shell: Swift app = Network.framework UDP listener + WKWebView hosting the SAME three.js app | Apple dev account; see entitlement note | polished endgame; TestFlight distribution; near-zero rework of the web frontend |
| d. Capacitor/RN wrapper with a small UDP plugin | same entitlement note | only if c's shell is unappealing |

**iOS UDP entitlement note (paths c/d):** receiving *broadcast or multicast*
UDP on iOS hardware requires the `com.apple.developer.networking.multicast`
entitlement — granted via an Apple request form, enforced on iOS 16+
(simulator is exempt). Plain *unicast* UDP needs nothing. So if U1 lands on
broadcast, either request the entitlement or use the U1-b discovery trick to
make the Hub unicast to the device (ForeFlight's own spec pushes unicast
because iOS broadcast reception is lossy anyway). Local-network privacy
prompt (iOS 14+) appears once either way.

Cockpit practicalities regardless of path: thermal — iPads shut down in
direct sun under a canopy, so mount shaded; sunlight legibility — iPad Pro
(~1000 nits) or an iPhone beats a base iPad (~600 nits); use Guided Access to
lock to the app; mounting is a safety item (any loose mass goes airborne
under negative g).

## 8. Repo layout (target)

```
livefreeandfly/acroReplay/
  PLAN.md                    ← this file
  capture_onflight.py        ← bench capture kit v2 (exists)
  captures/                  ← pcaps + web mirrors + ws/gdl90 logs (gitignored; keep decoded fixtures)
  sample_logs/               ← SD-card logs + CSV/MAT exports (gitignored; fixtures extracted into tests/)
  docs/PROTOCOL.md           ← Wi-Fi processor interfaces: HTTP config API + ws /data frame (exists); UDP stream TBD
  onflight/ws_data.py        ← ws /data frame decoder (exists)
  bridge/                    ← python: sources/, hub, ring buffer, segmenter, logging
  web/                       ← vite + three.js app
  tests/                     ← pytest; fixtures/ holds pcap slices + expected StateSamples
```

## 9. Decision log

- 2026-08-12 — Ground coaching descoped (Sean). Single-device, in-cockpit only.
- 2026-08-12 — three.js over Cesium: local ENU box scene beats a globe for
  this use; prior three.js experience.
- 2026-08-12 — Quaternions end-to-end; Euler only at UI display edges.
- 2026-08-12 — Python asyncio bridge + browser frontend over native app for
  MVP; revisit at phase 4.
- 2026-08-12 — Plan C (custom sensor unit) is contingency only; do not start
  while U1–U3 are unresolved.
- 2026-09-15 — U4 resolved: the Hub's `ws://…/data` is a 101-byte status
  frame (pitch/roll/lat/lon, no heading or rates) → side channel only; the
  developer UDP stream stays the target for 3D. Capture v2 written.
- 2026-09-16 — Cockpit platform: native iPhone shell (path c) chosen; ios/ scaffolded,
  web app made transport-agnostic (JS decoder + frame math).
- 2026-09-16 — Phase 1 first cut: aiohttp bridge + buildless three.js app;
  origin altitude tracks the lowest seen so the ground is always the floor.
- 2026-09-15 — U1/U2/U3 resolved from capture v2: UDP broadcast :2000,
  67-byte packed struct, 50 Hz, full INS state. Phase 0 done; Plan C closed.
  Fixtures committed with location moved to the KWVI reference point and
  identity strings synthesized — never commit raw captures (public repo).

## 10. References

- OnFlight Hub manual: https://bolderflight.com/assets/onflight/user_manual.pdf
- OnFlight product page: https://bolderflight.com/onflight.html
- Bolder Flight GitHub: https://github.com/bolderflight (navigation, framing, mavlink, mat_v4)
- ForeFlight GDL90 extended spec: https://www.foreflight.com/connect/spec/
- FAA GDL90 base spec: https://www.faa.gov/sites/faa.gov/files/air_traffic/technology/adsb/archival/GDL90_Public_ICD_RevA.PDF
- GDL90 parsers: https://github.com/NathanVaughn/gdl90py · https://github.com/etdey/gdl90
- ACROWRX docs: https://docs.acrowrx.com/ (OnFlight config: /onFlight.html)
- X-Plane data output: https://x-plane.helpscoutdocs.com/article/63-x-plane-11-data-output-settings · UDP ref: https://www.nuclearprojects.com/xplane/info.shtml
- OpenAero (Aresti, GPL): https://github.com/OpenAero/main
- AOPA on ACROWRX/OnFlight: aopa.org 2024-09-17 "Let the world watch you fly"; 2026-01 "Your digital aerobatic coach"
- Maneuver recognition literature: https://commons.erau.edu/db-theses/200/ ·
  https://asp-eurasipjournals.springeropen.com/articles/10.1186/s13634-022-00850-x
