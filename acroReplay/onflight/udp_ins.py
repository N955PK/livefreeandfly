"""Decoders for the OnFlight Hub's broadcast UDP messages (layouts in docs/PROTOCOL.md).

Port 2000 carries the 67-byte INS frame (message id 0x02) at 50 Hz; port 2005
carries the 55-byte identity message (message id 0x00) at 1 Hz. Both are raw
little-endian packed structs — no framing, no checksum.
"""

import datetime
import struct
from dataclasses import dataclass

INS_PORT = 2000
IDENTITY_PORT = 2005
INS_MSG_ID = 0x02
IDENTITY_MSG_ID = 0x00

INS_FORMAT = "<BBBbbbbBBBBBBBBBBhhhHHHhhhhhhhhhHHHHiiI"
INS_SIZE = struct.calcsize(INS_FORMAT)
IDENTITY_FORMAT = "<B6s12s24s12s"
IDENTITY_SIZE = struct.calcsize(IDENTITY_FORMAT)

GNSS_FIX_NAMES = {0: "NONE", 1: "TIME ONLY", 2: "2D", 3: "3D", 4: "DGNSS", 5: "RTK FLOAT", 6: "RTK FIXED"}

FLAG0_BATT_WARN = 0x01
FLAG0_BATT_LOW = 0x02
FLAG0_CPU_TEMP_OK = 0x04
FLAG0_INS_INITIALIZED = 0x08
FLAG0_INS_HEALTHY = 0x10
FLAG0_MAG_HEALTHY = 0x20
FLAG0_MAG_TEMP_OK = 0x40
FLAG0_GNSS_HEALTHY = 0x80
FLAG1_SENSOR_NEW_DATA = 0x08
FLAG1_GNSS_NEW_DATA = 0x40


@dataclass(frozen=True)
class InsFrame:
    """One 50 Hz INS solution. Body axes are front-right-down; angles in degrees, rates deg/s, accel g."""

    flags0: int
    flags1: int
    cpu_die_temp_c: int
    imu_die_temp_c: int
    mag_die_temp_c: int
    pres_die_temp_c: int
    horz_pos_acc_ft: float
    vert_pos_acc_ft: float
    vel_acc_kts: float
    gnss_fix: int
    gnss_num_sv: int
    utc: datetime.datetime
    pitch_deg: float
    roll_deg: float
    mag_declination_deg: float
    true_heading_deg: float
    ground_speed_kts: float
    ground_track_deg: float
    flight_path_angle_deg: float
    climb_rate_fpm: float
    load_factor_g: float
    p_dps: float
    q_dps: float
    r_dps: float
    accel_x_g: float
    accel_y_g: float
    accel_z_g: float
    alt_wgs84_ft: float
    alt_msl_ft: float
    cabin_pres_alt_ft: float
    static_pres_pa: float
    lat_deg: float
    lon_deg: float
    sys_time_s: float

    @property
    def ins_initialized(self):
        return bool(self.flags0 & FLAG0_INS_INITIALIZED)

    @property
    def ins_healthy(self):
        return bool(self.flags0 & FLAG0_INS_HEALTHY)

    @property
    def gnss_healthy(self):
        return bool(self.flags0 & FLAG0_GNSS_HEALTHY)

    @property
    def gnss_new_data(self):
        return bool(self.flags1 & FLAG1_GNSS_NEW_DATA)

    @property
    def gnss_fix_name(self):
        return GNSS_FIX_NAMES.get(self.gnss_fix, f"UNKNOWN({self.gnss_fix})")

    @property
    def mag_heading_deg(self):
        return (self.true_heading_deg - self.mag_declination_deg) % 360


@dataclass(frozen=True)
class Identity:
    serial: int
    tail_number: str
    pilot_name: str
    aircraft_type: str


def decode_ins(payload):
    """Decode a port-2000 datagram into an :class:`InsFrame`.

    :raises ValueError: on wrong length or message id.
    """
    if len(payload) != INS_SIZE:
        raise ValueError(f"expected {INS_SIZE}-byte INS frame, got {len(payload)}")
    v = struct.unpack(INS_FORMAT, payload)
    if v[0] != INS_MSG_ID:
        raise ValueError(f"expected message id {INS_MSG_ID:#x}, got {v[0]:#x}")
    gnss = v[10]
    utc = datetime.datetime(v[11] + 1970, v[12], v[13], v[14], v[15], v[16], tzinfo=datetime.timezone.utc)
    return InsFrame(
        flags0=v[1], flags1=v[2],
        cpu_die_temp_c=v[3], imu_die_temp_c=v[4], mag_die_temp_c=v[5], pres_die_temp_c=v[6],
        horz_pos_acc_ft=v[7] / 10, vert_pos_acc_ft=v[8] / 10, vel_acc_kts=v[9] / 10,
        gnss_fix=gnss & 0x07, gnss_num_sv=gnss >> 3, utc=utc,
        pitch_deg=v[17] / 100, roll_deg=v[18] / 100, mag_declination_deg=v[19] / 100,
        true_heading_deg=v[20] / 100, ground_speed_kts=v[21] / 100, ground_track_deg=v[22] / 100,
        flight_path_angle_deg=v[23] / 100, climb_rate_fpm=v[24] / 10, load_factor_g=v[25] / 1000,
        q_dps=v[26] / 10, p_dps=v[27] / 10, r_dps=v[28] / 10,
        accel_x_g=v[29] / 1000, accel_y_g=v[30] / 1000, accel_z_g=v[31] / 1000,
        alt_wgs84_ft=v[32] - 10000, alt_msl_ft=v[33] - 10000, cabin_pres_alt_ft=v[34] - 10000,
        static_pres_pa=v[35] * 2, lat_deg=v[36] / 1e7, lon_deg=v[37] / 1e7, sys_time_s=v[38] / 1e3,
    )


def _cstr(raw):
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace")


def decode_identity(payload):
    """Decode a port-2005 datagram into an :class:`Identity`."""
    if len(payload) != IDENTITY_SIZE:
        raise ValueError(f"expected {IDENTITY_SIZE}-byte identity message, got {len(payload)}")
    msg_id, serial, tail, pilot, actype = struct.unpack(IDENTITY_FORMAT, payload)
    if msg_id != IDENTITY_MSG_ID:
        raise ValueError(f"expected message id {IDENTITY_MSG_ID:#x}, got {msg_id:#x}")
    return Identity(int.from_bytes(serial, "little"), _cstr(tail), _cstr(pilot), _cstr(actype))
