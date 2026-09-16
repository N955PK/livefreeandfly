# OnFlight Hub — Wi-Fi processor interfaces

Derived 2026-09-15 from the Hub's own config webpage (`index.html`, `script.js`)
mirrored off `http://192.168.23.1/` and from packet captures of its broadcasts.
Unit: firmware 14, hardware 2, ACROWRX product flag set, datalog divider 0 (50 Hz).

All multi-byte values are **little-endian**. The Wi-Fi processor behaves like
an ESP-class async web server: static assets, JSON config endpoints, and one
binary WebSocket. It does not appear to 404 unknown paths — requests to
non-existent URLs hang until client timeout, so only hit the paths below.

## HTTP config API

| method | path | body / response JSON keys |
|---|---|---|
| GET | `/config` | `serial` (int; page shows as hex), `version`, `hw-version`, `product` (1 = ACROWRX-enabled), `tail-num`, `pilot-name`, `aircraft-type`, `utc-offset`, `datalog-format`, `datalog-srd` (sample-rate divider), `rotation00…rotation22` (mounting matrix, row-major) |
| POST | `/config` | same editable keys as above |
| GET/POST | `/sys-config` | `gdl90-port`, `input-volt-cutoff-hz`, `sys-warn-volt`, `sys-low-volt` |
| GET/POST | `/sensor-config` | `imu-bandwidth`, `gyro-bias-thresh-dps`, `accel-bias-g0..2`, `mag-bias-ut0..2`, `accel-scale00..22`, `mag-scale00..22`, `gnss-nav-rate`, `pres-os-mode`, `pres-filt`, `static-pres-cutoff-hz` |
| GET/POST | `/ins-config` | `gnss-min-sv`, `gnss-min-horz-acc-ft`, `gnss-min-vert-acc-ft`, `gnss-rtcov`, `gnss-reachability`, `gyro-cutoff-hz`, `accel-cutoff-hz`, `mag-cutoff-hz`, `load-factor-cutoff-hz`, `climb-rate-cutoff-hz` |
| POST | `/default-config` | `{}` — restores defaults |
| POST | `/acrowrx` | `{"product-key": "..."}` — enables ACROWRX log format; `/config.product` becomes 1 |
| POST | `/zero-stadia` | `{}` — re-zeroes the Stadia AGL altimeter |

POSTs are `Content-Type: application/json`; the page re-GETs the section
500 ms later. Config updates other than the GDL90 port reset the DAS processor.

## WebSocket `ws://192.168.23.1/data` — binary status frame (101 bytes)

The page opens this on load with `binaryType = 'arraybuffer'` and reconnects
2 s after close. Push rate: not yet measured (capture v2 records it).
`struct` format: `<BBBBbbbbbbBBBBBBBBBBBhhHHHHHhHHHHHhHHhhiiIBBBBbbbbHHHHffff`

| off | type | field | scale / notes |
|---|---|---|---|
| 0 | u8 | flags0 | bit0 batt WARN, bit1 batt LOW, bit2 cpu die temp ok, bit3 IMU healthy, bit4 IMU temp ok, bit5 mag healthy, bit6 mag temp ok, bit7 GNSS healthy |
| 1 | u8 | flags1 | bit0 pres healthy, bit1 pres temp ok, bit2 airdata connected, bit3 airdata batt WARN, bit4 airdata batt LOW, bit5 airdata temp ok, bit6 airdata OAT avail, bit7 airdata AOA avail |
| 2 | u8 | flags2 | bit0 static-pres healthy, bit1 diff-pres healthy, bit2 OAT healthy, bit3 AOA healthy, bit4 AOA type is angle-deg (else pressure ratio), bit5 KCAS avail, bit6 wind estimate avail |
| 3 | u8 | flags3 | bit0 AGL alt connected, bit1 AGL batt WARN, bit2 AGL batt LOW, bit3 AGL temp ok, bit4 AGL data healthy, bit5 AGL in range, bit6 Stadia connected, bit7 heart-rate connected |
| 4 | i8 | hub_cpu_die_temp_c | |
| 5 | i8 | hub_imu_die_temp_c | |
| 6 | i8 | hub_mag_die_temp_c | |
| 7 | i8 | hub_pres_die_temp_c | |
| 8 | i8 | airdata_die_temp_c | |
| 9 | i8 | agl_alt_die_temp_c | |
| 10 | u8 | stadia_batt_prcnt | |
| 11 | u8 | hub_horz_pos_acc_ft | ÷10 |
| 12 | u8 | hub_vert_pos_acc_ft | ÷10 |
| 13 | u8 | hub_vel_acc_kts | ÷10 |
| 14 | u8 | gnss | fix = `& 0x07` (0 none, 1 time-only, 2 2D, 3 3D, 4 DGNSS, 5 RTK float, 6 RTK fixed); num_sv = `>> 3` |
| 15–20 | u8×6 | utc month, day, hour, min, sec, year | year + 1970 |
| 21 | i16 | hub_pitch_deg | ÷100 |
| 23 | i16 | hub_roll_deg | ÷100 |
| 25 | u16 | hub_alt_wgs84_ft | − 10000 |
| 27 | u16 | hub_alt_msl_ft | − 10000 |
| 29 | u16 | hub_cabin_pres_alt_ft | − 10000 |
| 31 | u16 | airdata_static_pres_pa | × 2 |
| 33 | u16 | airdata_diff_pres_pa | |
| 35 | i16 | airdata_oat_c | ÷100 |
| 37 | u16 | airdata_kias | ÷100 |
| 39 | u16 | airdata_kcas | ÷100 |
| 41 | u16 | airdata_ktas | ÷100 |
| 43 | u16 | airdata_pres_alt_ft | − 10000 |
| 45 | u16 | airdata_density_alt_ft | − 10000 |
| 47 | i16 | airdata_aoa | ÷100 (deg or pressure ratio per flags2 bit4) |
| 49 | u16 | airdata_wind_spd_kts | ÷100 |
| 51 | u16 | airdata_wind_dir_true_deg | ÷100 |
| 53 | i16 | agl_alt_agl_alt_ft | ÷12 (raw inches) |
| 55 | i16 | stadia_alt_ft | ÷12 (raw inches) |
| 57 | i32 | hub_lat_deg | ÷1e7 |
| 61 | i32 | hub_lon_deg | ÷1e7 |
| 65 | u32 | hub_sys_time_s | ÷1000 (raw ms since boot) |
| 69 | u8 | heart_rate_bpm | |
| 70 | u8 | ain_connected | bitmask, 4 analog-input channels |
| 71 | u8 | ain_healthy_die_temp_ok | |
| 72 | u8 | ain_batt_status | |
| 73–76 | i8×4 | ain0..3_die_temp_c | |
| 77 | u16×4 | ain0..3_volt | ÷10000 |
| 85 | f32×4 | ain0..3_val | engineering value (the "analog input module" — control-position sensors) |

**Assessment for acroReplay:** no heading, body rates, accelerations, load
factor, or velocities → this frame cannot drive the 3D replay by itself. It is
a good health/GNSS-quality side channel. The UDP INS frame below is the 3D data source; this frame's extra fields (air-data,
AGL, heart rate, analog inputs) only appear here.

## UDP broadcast streams (to 192.168.23.255, always on)

Captured 2026-09-15 with firmware 14 / hw 2, ACROWRX product flag set. No
discovery handshake is needed; the Hub broadcasts from boot.

| port | rate | size | message |
|---|---|---|---|
| 2000 | 50 Hz (20.0 ms median) | 67 B | INS frame, message id `0x02` — **the acroReplay data source** |
| 2005 | 1 Hz | 55 B | identity, message id `0x00` |
| 4000 (configurable) | 5 Hz + 1 Hz | 57 / 111 B | GDL90: ownship 0x0A + geo-alt 0x0B + ForeFlight AHRS 0x65/01 per datagram; heartbeat 0x00 + ForeFlight ID 0x65/00 once a second |

Frames are raw packed little-endian structs: no start/stop bytes, no
checksum, not MAVLink, not the bolderflight `framing` scheme. The encodings
are exactly the ranges in the manual's spec table.

### INS frame — port 2000, 67 bytes, `struct` format `<BBBbbbbBBBBBBBBBBhhhHHHhhhhhhhhhHHHHiiI`

Decoder: `onflight/udp_ins.py`. Body axes front-right-down. Attitude/position
fields read exactly 0 until the INS has initialized (needs a 3D fix with the
configured minimum satellites — ~45 s outdoors on the bench).

| off | type | field | scale / notes | verified against |
|---|---|---|---|---|
| 0 | u8 | message id | `0x02` | constant |
| 1 | u8 | flags0 | bit0 batt WARN, bit1 batt LOW, bit2 cpu temp ok, **bit3 INS initialized**, **bit4 INS healthy** (drops transiently under aggressive rotation), bit5 mag healthy, bit6 mag temp ok, bit7 GNSS healthy | ws `flags0` bit-for-bit except bits 3–4; bit3 == attitude non-zero 100% |
| 2 | u8 | flags1 | bits 0,1,2,4,5,7 always set on a healthy unit (sensor health, names unknown); **bit3 toggles at 25 Hz** (new mag/pressure sample); **bit6 pulses at the GNSS nav rate** (10 Hz → 1 frame in 5) | duty cycles |
| 3–6 | i8×4 | cpu, imu, mag, pres die temp °C | | ws |
| 7 | u8 | horz pos accuracy ft | ÷10 | ws |
| 8 | u8 | vert pos accuracy ft | ÷10 | ws |
| 9 | u8 | velocity accuracy kt | ÷10 | ws |
| 10 | u8 | gnss | fix = `& 0x07` (0 none, 1 time, 2 2D, 3 3D, 4 DGNSS, 5 RTK float, 6 RTK fixed), num_sv = `>> 3` | ws |
| 11–16 | u8×6 | UTC year−1970, month, day, hour, min, sec | | ws |
| 17 | i16 | pitch ° | ÷100 | ws, GDL90 AHRS (0.06° median diff) |
| 19 | i16 | roll ° | ÷100 | ws, GDL90 AHRS |
| 21 | i16 | magnetic declination ° (east +) | ÷100; 12.54 at Watsonville | true − mag heading vs GDL90 |
| 23 | u16 | **true** heading ° | ÷100 | GDL90 AHRS heading (0.04° median diff) |
| 25 | u16 | ground speed kt | ÷100 (0–655 kt) | GDL90 ownship |
| 27 | u16 | ground track ° | ÷100 | GDL90 ownship (0.7° median diff) |
| 29 | i16 | flight-path angle ° | ÷100 | range ±89 |
| 31 | i16 | climb rate ft/min | ÷10 (±3,276) | GDL90 ownship (coarse) |
| 33 | i16 | load factor g, positive up | ÷1000 | 0.982 stationary |
| 35 | i16 | **q** — pitch rate °/s | ÷10 | Euler-rate kinematics r=0.995 |
| 37 | i16 | **p** — roll rate °/s | ÷10 | kinematics r=0.993 |
| 39 | i16 | **r** — yaw rate °/s | ÷10 | kinematics r=0.988 |
| 41 | i16 | accel x (body fwd) | mg | −0.996 × gravity component |
| 43 | i16 | accel y (body right) | mg | −1.006 × |
| 45 | i16 | accel z (body down) | mg | −0.993 × |
| 47 | u16 | WGS-84 altitude ft | − 10000 | ws |
| 49 | u16 | MSL altitude ft | − 10000 | ws |
| 51 | u16 | cabin pressure altitude ft | − 10000 | ws, GDL90 ownship pressure alt |
| 53 | u16 | static pressure Pa | × 2 | 100,846 Pa at 41 m |
| 55 | i32 | latitude ° | ÷1e7 | ws |
| 59 | i32 | longitude ° | ÷1e7 | ws |
| 63 | u32 | system time ms since boot | ÷1000 | +20 per frame; matches ws |

Note the rate ordering: the frame stores **q, p, r** (pitch, roll, yaw rate),
not p, q, r — confirmed by two independent attitude-derivative methods at
r > 0.99. The Hub low-passes gyros at the configured cutoff (3 Hz default),
so raw rates read ~10% below attitude-derived peaks during fast motion.

Not present (derive in the adapter): NED velocity (from ground speed, track,
climb rate), quaternion (from the Euler triple), magnetic heading (true −
declination).

### Identity message — port 2005, 55 bytes, `<B6s12s24s12s`

| off | type | field |
|---|---|---|
| 0 | u8 | message id `0x00` |
| 1 | u48 LE | unit serial (same value as the Wi-Fi SSID suffix, `/config.serial`) |
| 7 | char[12] | tail number, NUL-padded (`/config.tail-num`) |
| 19 | char[24] | pilot name |
| 43 | char[12] | aircraft type |

## SD-card datalog — `*.acrowrx` (ACROWRX format, product flag set)

Reader: `onflight/acrowrx_log.py` (also converts a log to replayable UDP frames). Derived from
three real flights (firmware 14); every field below was checked against physics and against
the UDP frame's encodings. **Layout is firmware-dependent** — the reader verifies checksums
and record length and will refuse silently-different records.

Blocks: `tag(2) type(1) len(1) payload(len) fletcher16(2)`, checksum over tag+type+len+payload
(Bolder Flight `framing`). `MD` type 0, 54 B = identity (serial u48, tail[12], pilot[24],
type[12]); `CD` type 1, 231 B = configuration dump; `SD` type 0, 3 B unknown; then `AW` type 1,
190 B per 50 Hz frame until power-off (final record usually truncated).

### `AW` record (190 B, little-endian) — INS block then raw-sensor block

| off | type | field | scale / notes |
|---|---|---|---|
| 0–1 | u8 u8 | flags0, flags1 | same bit meanings as the UDP frame's bytes 1–2 |
| 2–5 | u8×4 | flags2, flags3, reserved | zero without external sensors |
| 6 | i16 | pitch ° | ÷100 |
| 8 | i16 | roll ° | ÷100 (reads garbage until INS converges — 85° while parked on one log) |
| 10 | i16 | magnetic declination ° | ÷100 |
| 12 | u16 | true heading ° | ÷100 |
| 14 | u16 | magnetic heading ° | ÷100 (= true − declination) |
| 16 | i16 | climb rate ft/min | ×1 (r = 0.97 vs d(pressure alt)/dt) |
| 18 | i16 | unknown | 83 parked, ±4500 in flight |
| 20 | i16×3 | accel x, y, z | mg, body FRD, bias-corrected (pairs with raw @97) |
| 26 | i16×3 | gyro x, y, z (p, q, r) | ÷10 °/s (|ω| vs attitude rate r = 1.000) |
| 32 | i16×3 | magnetometer x, y, z | ÷100 µT (|B| = 47.7 µT at Watsonville) |
| 38 | i16 i16 | velocity north, east | ÷10 kt (r = 1.000 vs gs·cos/sin track) |
| 42 | i16 | velocity down | ft/min |
| 44 | u16 | ground speed | ÷100 kt |
| 46 | u16 | true ground track ° | ÷100 |
| 48 | u16 | magnetic ground track ° | ÷100 |
| 50 | i16 | flight-path angle ° | ÷100 |
| 52 | u8 | unknown | |
| 53 | u16 | input voltage | mV, filtered (3.9 V on battery, 5.8 V on USB) |
| 55 | i32 i32 | INS latitude, longitude | ÷1e7 |
| 63 | u8 | GNSS fix (& 7), satellites (>> 3) | |
| 64 | u8×6 | UTC year−1970, month, day, hour, min, sec | |
| 70 | u8×3 | unknown | GNSS accuracies? |
| 73 | i8×4 | die temperatures °C | assumed cpu, imu, mag, pres |
| 77 | i16×3 | GNSS velocity north, east (÷10 kt), down (ft/min) | |
| 83 | u8 | unknown | |
| 84 | u16 | input voltage | mV, raw |
| 86 | i16 | unknown | −999 (sentinel?) |
| 88 | i32 i32 | GNSS latitude, longitude | ÷1e7 |
| 96 | u8 | unknown | |
| 97 | i16×3 | raw accel x, y, z | mg |
| 103 | i16×3 | raw gyro x, y, z | ÷10 °/s |
| 109 | u8 | unknown | |
| 110 | i16×3 | raw magnetometer x, y, z | ÷100 µT |
| 116 | u16 | static pressure, raw | ×2 Pa |
| 118 | u16 | pressure altitude ft | −10000 |
| 120 | u8 | unknown | |
| 121 | u16 | static pressure, filtered | ×2 Pa |
| 123–150 | | external air-data block | zeros; two `+10000` altitude slots at 136/138 |
| 151 | u32 | system time ms since boot | |
| 155–189 | | remainder | mostly zero; a few slow-changing bytes |

Not yet located: an MSL / WGS-84 altitude (the UDP frame has both; the converter fills the
altitude slots with pressure altitude), GNSS accuracies, load factor (derived as −accel z).

## GDL90 (ForeFlight extension)

Configured via `/sys-config.gdl90-port` (4000 on this unit). Observed: broadcast,
not unicast — the Hub kept broadcasting while ForeFlight discovery JSON was sent
on UDP 63093. Datagrams pack several messages: ownship 0x0A + geo-alt 0x0B +
ForeFlight AHRS 0x65/01 at 5 Hz; heartbeat + ForeFlight ID 0x65/00 at 1 Hz. The
AHRS heading matched the UDP true heading, with the true/mag flag inconsistently
set. Fallback only — 5 Hz attitude is too slow for aerobatics.

## Capture file formats (this repo)

`ws_data_<phase>.bin`, `gdl90_<phase>.bin`, and `tests/fixtures/*.bin`: repeated
records of `<dH` (unix time f64, payload length u16) followed by the raw payload
(`onflight/records.py`). `<phase>.pcap`: libpcap, read with `onflight/pcap.py`.
