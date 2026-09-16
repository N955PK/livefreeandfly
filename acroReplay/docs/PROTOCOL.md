# OnFlight Hub — Wi-Fi processor interfaces

Derived 2026-09-15 from the Hub's own config webpage (`index.html`, `script.js`)
mirrored off `http://192.168.23.1/`. Unit: serial `4496A6FE8CE0` (SSID suffix).
Firmware version: recorded in the `/config` JSON of the next capture.

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
a good health/GNSS-quality side channel. Its packed-struct style strongly
suggests the developer UDP stream (still uncaptured) is also a packed LE
struct, most likely the datalog record — decode plan in PLAN.md §6.

## GDL90 (ForeFlight extension)

Configured via `/sys-config.gdl90-port` (ForeFlight expects 4000). Per the
manual: heartbeat + ForeFlight ID at 1 Hz; ownship, GNSS altitude, attitude at
5 Hz. Whether the Hub unicasts to a client after seeing ForeFlight's discovery
broadcast on UDP 63093 is tested by capture v2.

## Capture file formats (this repo)

`ws_data_<phase>.bin` and `gdl90_<phase>.bin`: repeated records of
`<dH` (unix time f64, payload length u16) followed by the raw payload.
