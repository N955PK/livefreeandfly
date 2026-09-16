"""Reader for the OnFlight Hub's SD-card datalog in ACROWRX format (``*.acrowrx``).

File = sequence of blocks ``tag(2) type(1) length(1) payload(length) fletcher16(2)``, the checksum
taken over tag+type+length+payload (Bolder Flight's framing convention). Blocks seen:

* ``MD`` (type 0, 54 B) — identity: serial u48 LE, tail[12], pilot[24], aircraft type[12]
* ``CD`` (type 1, 231 B) — configuration dump (firmware/hardware version, mounting rotation, filters)
* ``SD`` (type 0, 3 B)  — unknown, once after the config
* ``AW`` (type 1, 190 B) — one data record per 50 Hz frame; layout in :data:`AW_FORMAT` / docs/PROTOCOL.md

Attitude, position and rate fields read exactly zero until the INS has initialized. Records
mirror the UDP INS frame (same encodings) plus a raw-sensor copy of accel/gyro/mag/GNSS.

    python -m onflight.acrowrx_log flight.acrowrx out.bin [--start S] [--duration S]

converts a log into the capture-kit record format of 67-byte UDP INS frames, so the bridge,
fake hub, and web app replay a real flight without knowing about this format.
"""

import argparse
import datetime
import struct
import sys
from dataclasses import dataclass

from onflight.records import write_records
from onflight.udp_ins import INS_FORMAT, INS_MSG_ID

BLOCK_HEADER = struct.Struct("<2sBB")
AW_TAG, MD_TAG, CD_TAG = b"AW", b"MD", b"CD"
AW_LEN = 190
IDENTITY_FORMAT = "<6s12s24s12s"

# fmt: off
AW_FORMAT = "<" + "".join([
    "BBBBBB",     # 0   flags0, flags1, flags2, flags3, reserved x2
    "hhh",        # 6   pitch x100, roll x100, magnetic declination x100 (deg)
    "HH",         # 12  true heading x100, magnetic heading x100 (deg)
    "h",          # 16  climb rate (ft/min)
    "h",          # 18  unknown (see PROTOCOL.md)
    "hhh",        # 20  accel x, y, z (mg, body FRD, INS bias-corrected)
    "hhh",        # 26  gyro x, y, z (deg/s x10, INS bias-corrected)
    "hhh",        # 32  mag x, y, z (uT x100, filtered)
    "hhh",        # 38  velocity north, east (kt x10), down (ft/min)
    "HHH",        # 44  ground speed x100 (kt), true track x100, magnetic track x100 (deg)
    "h",          # 50  flight-path angle x100 (deg)
    "B",          # 52  unknown
    "H",          # 53  input voltage (mV, filtered)
    "ii",         # 55  INS latitude, longitude (deg x1e7)
    "B",          # 63  GNSS fix (& 7) | satellites (>> 3)
    "BBBBBB",     # 64  UTC year-1970, month, day, hour, minute, second
    "BBB",        # 70  unknown x3 (GNSS accuracies?)
    "bbbb",       # 73  die temperatures (C): cpu, imu, mag, pres (assumed order)
    "hhh",        # 77  GNSS velocity north, east (kt x10), down (ft/min)
    "B",          # 83  unknown
    "H",          # 84  input voltage (mV, raw)
    "h",          # 86  unknown (-999 sentinel?)
    "ii",         # 88  GNSS latitude, longitude (deg x1e7)
    "B",          # 96  unknown
    "hhh",        # 97  raw accel x, y, z (mg)
    "hhh",        # 103 raw gyro x, y, z (deg/s x10)
    "B",          # 109 unknown
    "hhh",        # 110 raw mag x, y, z (uT x100)
    "H",          # 116 static pressure raw (Pa / 2)
    "H",          # 118 pressure altitude (ft + 10000)
    "B",          # 120 unknown
    "H",          # 121 static pressure filtered (Pa / 2)
    "13s",        # 123 zeros (external air-data block, unused)
    "HH",         # 136 ext air-data pressure alt, density alt (ft + 10000; 0 when absent)
    "11s",        # 140 zeros
    "I",          # 151 system time (ms since boot)
    "35s",        # 155 remainder (mostly zeros; a few slow-changing bytes)
])
# fmt: on
AW_SIZE = struct.calcsize(AW_FORMAT)
assert AW_SIZE == AW_LEN, AW_SIZE


def fletcher16(data):
    s1 = s2 = 0
    for b in data:
        s1 = (s1 + b) % 255
        s2 = (s2 + s1) % 255
    return bytes((s1, s2))


@dataclass(frozen=True)
class Block:
    offset: int
    tag: bytes
    type: int
    payload: bytes
    checksum_ok: bool


def iter_blocks(data):
    """Yield every complete :class:`Block` in a log; a truncated final block is dropped."""
    pos = 0
    while pos + BLOCK_HEADER.size + 2 <= len(data):
        tag, typ, length = BLOCK_HEADER.unpack_from(data, pos)
        end = pos + BLOCK_HEADER.size + length
        if end + 2 > len(data):
            return
        payload = data[pos + BLOCK_HEADER.size:end]
        ok = data[end:end + 2] == fletcher16(data[pos:end])
        yield Block(pos, tag, typ, payload, ok)
        pos = end + 2


@dataclass(frozen=True)
class Identity:
    serial: int
    tail_number: str
    pilot_name: str
    aircraft_type: str


def _cstr(raw):
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace")


def decode_identity(payload):
    serial, tail, pilot, actype = struct.unpack(IDENTITY_FORMAT, payload)
    return Identity(int.from_bytes(serial, "little"), _cstr(tail), _cstr(pilot), _cstr(actype))


@dataclass(frozen=True)
class AwRecord:
    """One 50 Hz log record. Units as in the UDP frame: degrees, knots, ft, ft/min, g, deg/s."""

    flags0: int
    flags1: int
    pitch_deg: float
    roll_deg: float
    mag_declination_deg: float
    true_heading_deg: float
    mag_heading_deg: float
    climb_rate_fpm: float
    unknown18: int
    accel_g: tuple
    gyro_dps: tuple
    mag_ut: tuple
    vel_north_kts: float
    vel_east_kts: float
    vel_down_fpm: float
    ground_speed_kts: float
    ground_track_deg: float
    mag_track_deg: float
    flight_path_angle_deg: float
    input_voltage_v: float
    lat_deg: float
    lon_deg: float
    gnss_fix: int
    gnss_num_sv: int
    utc: datetime.datetime
    temps_c: tuple
    gnss_vel_north_kts: float
    gnss_vel_east_kts: float
    gnss_vel_down_fpm: float
    gnss_lat_deg: float
    gnss_lon_deg: float
    raw_accel_g: tuple
    raw_gyro_dps: tuple
    raw_mag_ut: tuple
    static_pres_pa: float
    pres_alt_ft: float
    sys_time_s: float

    @property
    def ins_initialized(self):
        return self.lat_deg != 0.0 or self.lon_deg != 0.0

    @property
    def load_factor_g(self):
        return -self.accel_g[2]


def _utc(y, mo, d, h, mi, s):
    try:
        return datetime.datetime(y + 1970, mo, d, h, mi, s, tzinfo=datetime.timezone.utc)
    except ValueError:
        return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


def decode_aw(payload):
    v = struct.unpack(AW_FORMAT, payload)
    return AwRecord(
        flags0=v[0], flags1=v[1],
        pitch_deg=v[6] / 100, roll_deg=v[7] / 100, mag_declination_deg=v[8] / 100,
        true_heading_deg=v[9] / 100, mag_heading_deg=v[10] / 100,
        climb_rate_fpm=v[11], unknown18=v[12],
        accel_g=(v[13] / 1000, v[14] / 1000, v[15] / 1000),
        gyro_dps=(v[16] / 10, v[17] / 10, v[18] / 10),
        mag_ut=(v[19] / 100, v[20] / 100, v[21] / 100),
        vel_north_kts=v[22] / 10, vel_east_kts=v[23] / 10, vel_down_fpm=v[24],
        ground_speed_kts=v[25] / 100, ground_track_deg=v[26] / 100, mag_track_deg=v[27] / 100,
        flight_path_angle_deg=v[28] / 100, input_voltage_v=v[30] / 1000,
        lat_deg=v[31] / 1e7, lon_deg=v[32] / 1e7,
        gnss_fix=v[33] & 0x07, gnss_num_sv=v[33] >> 3,
        utc=_utc(*v[34:40]), temps_c=tuple(v[43:47]),
        gnss_vel_north_kts=v[47] / 10, gnss_vel_east_kts=v[48] / 10, gnss_vel_down_fpm=v[49],
        gnss_lat_deg=v[53] / 1e7, gnss_lon_deg=v[54] / 1e7,
        raw_accel_g=(v[56] / 1000, v[57] / 1000, v[58] / 1000),
        raw_gyro_dps=(v[59] / 10, v[60] / 10, v[61] / 10),
        raw_mag_ut=(v[63] / 100, v[64] / 100, v[65] / 100),
        static_pres_pa=v[66] * 2, pres_alt_ft=v[67] - 10000, sys_time_s=v[74] / 1000,
    )


def read_log(path):
    """Return ``(identity or None, config payload or None, [AwRecord...])`` for a log file."""
    data = open(path, "rb").read()
    identity = config = None
    records = []
    bad = 0
    for block in iter_blocks(data):
        if not block.checksum_ok:
            bad += 1
            continue
        if block.tag == MD_TAG:
            identity = decode_identity(block.payload)
        elif block.tag == CD_TAG:
            config = block.payload
        elif block.tag == AW_TAG and len(block.payload) == AW_LEN:
            records.append(decode_aw(block.payload))
    if bad:
        print(f"{path}: {bad} blocks failed checksum", file=sys.stderr)
    return identity, config, records


def to_udp_frame(r):
    """Re-pack a log record as the 67-byte UDP INS frame (see udp_ins.INS_FORMAT).

    The log has no separate MSL/WGS-84 altitude field identified yet, so pressure altitude fills
    all three altitude slots; GNSS accuracy bytes are zero; INS-initialized flag follows position.
    """
    flags0 = (r.flags0 | 0x18) if r.ins_initialized else (r.flags0 & ~0x18)
    clamp = lambda x, lo, hi: int(max(lo, min(hi, round(x))))  # noqa: E731
    alt = clamp(r.pres_alt_ft + 10000, 0, 65535)
    u = r.utc
    return struct.pack(
        INS_FORMAT, INS_MSG_ID, flags0 & 0xFF, r.flags1 & 0xFF,
        *(clamp(t, -128, 127) for t in r.temps_c), 0, 0, 0, (r.gnss_num_sv << 3) | r.gnss_fix,
        clamp(u.year - 1970, 0, 255), u.month, u.day, u.hour, u.minute, u.second,
        clamp(r.pitch_deg * 100, -32768, 32767), clamp(r.roll_deg * 100, -32768, 32767),
        clamp(r.mag_declination_deg * 100, -32768, 32767),
        clamp(r.true_heading_deg * 100, 0, 65535), clamp(r.ground_speed_kts * 100, 0, 65535),
        clamp(r.ground_track_deg * 100, 0, 65535), clamp(r.flight_path_angle_deg * 100, -32768, 32767),
        clamp(r.climb_rate_fpm * 10, -32768, 32767), clamp(r.load_factor_g * 1000, -32768, 32767),
        clamp(r.gyro_dps[1] * 10, -32768, 32767), clamp(r.gyro_dps[0] * 10, -32768, 32767),
        clamp(r.gyro_dps[2] * 10, -32768, 32767),
        *(clamp(a * 1000, -32768, 32767) for a in r.accel_g),
        alt, alt, alt, clamp(r.static_pres_pa / 2, 0, 65535),
        int(r.lat_deg * 1e7), int(r.lon_deg * 1e7), clamp(r.sys_time_s * 1000, 0, 2**32 - 1),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", help=".acrowrx file")
    ap.add_argument("out", help="output .bin (capture-kit records of 67-byte UDP frames)")
    ap.add_argument("--start", type=float, default=None,
                    help="start offset, s (default: 10 s before first reaching 1500 ft above the lowest altitude)")
    ap.add_argument("--duration", type=float, default=None, help="seconds to convert (default: to end)")
    args = ap.parse_args()

    identity, _, recs = read_log(args.log)
    if not recs:
        sys.exit("no records")
    t0 = recs[0].sys_time_s
    if args.start is None:
        ground_ft = min(r.pres_alt_ft for r in recs if r.ins_initialized)
        airborne = next((r for r in recs if r.ins_initialized and r.pres_alt_ft > ground_ft + 1500), recs[0])
        args.start = max(0.0, airborne.sys_time_s - t0 - 10)
    start_t = t0 + args.start
    end_t = start_t + args.duration if args.duration else float("inf")
    chosen = [r for r in recs if start_t <= r.sys_time_s < end_t and r.ins_initialized]
    write_records(args.out, ((r.sys_time_s, to_udp_frame(r)) for r in chosen))
    who = f"{identity.tail_number} / {identity.aircraft_type}" if identity else "unknown aircraft"
    print(f"{args.log}: {len(recs)} records ({(recs[-1].sys_time_s - t0) / 60:.1f} min), {who}; "
          f"wrote {len(chosen)} frames from t+{args.start:.0f}s → {args.out}")


if __name__ == "__main__":
    main()
