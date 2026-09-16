"""Decoder for the OnFlight Hub ``ws://<hub>/data`` binary status frame.

Layout transcribed from the Hub's own ``script.js`` ``onMessage`` handler
(see docs/PROTOCOL.md). 101 bytes, little-endian.
"""

import struct
from dataclasses import dataclass

FRAME_FORMAT = "<BBBBbbbbbbBBBBBBBBBBBhhHHHHHhHHHHHhHHhhiiIBBBBbbbbHHHHffff"
FRAME_SIZE = struct.calcsize(FRAME_FORMAT)

GNSS_FIX_NAMES = {0: "NONE", 1: "TIME ONLY", 2: "2D", 3: "3D", 4: "DGNSS", 5: "RTK FLOAT", 6: "RTK FIXED"}


@dataclass(frozen=True)
class HubStatus:
    flags0: int
    flags1: int
    flags2: int
    flags3: int
    cpu_die_temp_c: int
    imu_die_temp_c: int
    mag_die_temp_c: int
    pres_die_temp_c: int
    airdata_die_temp_c: int
    agl_alt_die_temp_c: int
    stadia_batt_prcnt: int
    horz_pos_acc_ft: float
    vert_pos_acc_ft: float
    vel_acc_kts: float
    gnss_fix: int
    gnss_num_sv: int
    utc_year: int
    utc_month: int
    utc_day: int
    utc_hour: int
    utc_min: int
    utc_sec: int
    pitch_deg: float
    roll_deg: float
    alt_wgs84_ft: float
    alt_msl_ft: float
    cabin_pres_alt_ft: float
    airdata_static_pres_pa: float
    airdata_diff_pres_pa: float
    airdata_oat_c: float
    airdata_kias: float
    airdata_kcas: float
    airdata_ktas: float
    airdata_pres_alt_ft: float
    airdata_density_alt_ft: float
    airdata_aoa: float
    airdata_wind_spd_kts: float
    airdata_wind_dir_true_deg: float
    agl_alt_ft: float
    stadia_alt_ft: float
    lat_deg: float
    lon_deg: float
    sys_time_s: float
    heart_rate_bpm: int
    ain_connected: int
    ain_healthy_die_temp_ok: int
    ain_batt_status: int
    ain_die_temp_c: tuple
    ain_volt: tuple
    ain_val: tuple

    @property
    def imu_healthy(self):
        return bool(self.flags0 & 0x08)

    @property
    def gnss_healthy(self):
        return bool(self.flags0 & 0x80)

    @property
    def gnss_fix_name(self):
        return GNSS_FIX_NAMES.get(self.gnss_fix, f"UNKNOWN({self.gnss_fix})")


def decode(payload):
    """Decode one 101-byte frame into a :class:`HubStatus`.

    :param bytes payload: raw WebSocket binary message.
    :raises ValueError: if the payload is not exactly ``FRAME_SIZE`` bytes.
    """
    if len(payload) != FRAME_SIZE:
        raise ValueError(f"expected {FRAME_SIZE}-byte frame, got {len(payload)}")
    v = struct.unpack(FRAME_FORMAT, payload)
    gnss = v[14]
    return HubStatus(
        flags0=v[0], flags1=v[1], flags2=v[2], flags3=v[3],
        cpu_die_temp_c=v[4], imu_die_temp_c=v[5], mag_die_temp_c=v[6], pres_die_temp_c=v[7],
        airdata_die_temp_c=v[8], agl_alt_die_temp_c=v[9], stadia_batt_prcnt=v[10],
        horz_pos_acc_ft=v[11] / 10, vert_pos_acc_ft=v[12] / 10, vel_acc_kts=v[13] / 10,
        gnss_fix=gnss & 0x07, gnss_num_sv=gnss >> 3,
        utc_month=v[15], utc_day=v[16], utc_hour=v[17], utc_min=v[18], utc_sec=v[19], utc_year=v[20] + 1970,
        pitch_deg=v[21] / 100, roll_deg=v[22] / 100,
        alt_wgs84_ft=v[23] - 10000, alt_msl_ft=v[24] - 10000, cabin_pres_alt_ft=v[25] - 10000,
        airdata_static_pres_pa=v[26] * 2, airdata_diff_pres_pa=v[27], airdata_oat_c=v[28] / 100,
        airdata_kias=v[29] / 100, airdata_kcas=v[30] / 100, airdata_ktas=v[31] / 100,
        airdata_pres_alt_ft=v[32] - 10000, airdata_density_alt_ft=v[33] - 10000, airdata_aoa=v[34] / 100,
        airdata_wind_spd_kts=v[35] / 100, airdata_wind_dir_true_deg=v[36] / 100,
        agl_alt_ft=v[37] / 12, stadia_alt_ft=v[38] / 12,
        lat_deg=v[39] / 1e7, lon_deg=v[40] / 1e7, sys_time_s=v[41] / 1e3,
        heart_rate_bpm=v[42], ain_connected=v[43], ain_healthy_die_temp_ok=v[44], ain_batt_status=v[45],
        ain_die_temp_c=tuple(v[46:50]), ain_volt=tuple(x / 10000 for x in v[50:54]), ain_val=tuple(v[54:58]),
    )


def iter_records(path):
    """Yield ``(unix_time, payload)`` from a ``ws_data_*.bin`` capture file."""
    header = struct.Struct("<dH")
    with open(path, "rb") as fh:
        while True:
            head = fh.read(header.size)
            if len(head) < header.size:
                return
            t, n = header.unpack(head)
            yield t, fh.read(n)
