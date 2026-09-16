"""Decoders against real frames captured from the OnFlight Hub on 2026-09-15.

Fixture lat/lon were moved to the Watsonville (KWVI) airport reference point and
the identity strings synthesized before committing; everything else is verbatim.
"""

import statistics
from pathlib import Path

from onflight.records import iter_records
from onflight.udp_ins import INS_SIZE, decode_identity, decode_ins
from onflight.ws_data import FRAME_SIZE, decode as decode_ws

FIXTURES = Path(__file__).parent / "fixtures"
KWVI_LAT, KWVI_LON = 36.93575, -121.78975


def frames(name, decoder):
    return [(t, decoder(p)) for t, p in iter_records(FIXTURES / name)]


def test_ins_frame_layout_is_67_bytes():
    assert INS_SIZE == 67


def test_ins_stationary_tail_reads_like_a_still_hub_with_a_fix():
    rows = frames("udp2000_stationary_tail.bin", decode_ins)
    f = [x for _, x in rows]
    assert all(x.ins_initialized for x in f)
    assert {x.gnss_fix_name for x in f} == {"3D"}
    assert all(9 <= x.gnss_num_sv <= 11 for x in f)
    assert abs(statistics.median(x.pitch_deg for x in f) - 10.9) < 1.0
    assert abs(statistics.median(x.roll_deg for x in f) - 1.7) < 0.5
    assert 60 < statistics.median(x.true_heading_deg for x in f) < 95
    assert abs(statistics.median(x.mag_declination_deg for x in f) - 12.54) < 0.01
    assert all(abs(x.lat_deg - KWVI_LAT) < 1e-6 and abs(x.lon_deg - KWVI_LON) < 1e-6 for x in f)
    assert 120 < statistics.median(x.alt_msl_ft for x in f) < 150
    assert 20 < statistics.median(x.alt_wgs84_ft for x in f) < 50
    assert 100_500 < statistics.median(x.static_pres_pa for x in f) < 101_200
    assert abs(statistics.median(x.load_factor_g for x in f) - 0.98) < 0.03
    assert abs(statistics.median(x.accel_z_g for x in f) + 0.98) < 0.03
    assert all(max(abs(x.p_dps), abs(x.q_dps), abs(x.r_dps)) < 3 for x in f)
    assert all(x.ground_speed_kts < 1.5 for x in f)
    assert {(x.utc.year, x.utc.month, x.utc.day, x.utc.hour) for x in f} == {(2026, 9, 16, 0)}
    dt = [b.sys_time_s - a.sys_time_s for (_, a), (_, b) in zip(rows, rows[1:])]
    assert abs(statistics.median(dt) - 0.020) < 0.001


def test_ins_moving_frames_show_hand_rotation():
    f = [x for _, x in frames("udp2000_moving.bin", decode_ins)]
    assert max(x.roll_deg for x in f) - min(x.roll_deg for x in f) > 180
    assert max(abs(x.p_dps) for x in f) > 100
    assert all(0 <= x.true_heading_deg < 360 for x in f)
    assert all(0.9 < x.mag_heading_deg % 360 + 1 for x in f)
    assert all(abs(x.alt_msl_ft - 135) < 40 for x in f)


def test_identity_message():
    (_, ident), *_ = frames("udp2005_identity.bin", decode_identity)
    assert ident.serial == 0x010203040506
    assert (ident.tail_number, ident.pilot_name, ident.aircraft_type) == ("N12345", "Test Pilot", "TEST")


def test_ws_status_frames():
    f = [x for _, x in frames("ws_data_stationary_tail.bin", decode_ws)]
    assert FRAME_SIZE == 101 and len(f) == 40
    assert {x.gnss_fix_name for x in f} == {"3D"}
    assert abs(statistics.median(x.pitch_deg for x in f) - 10.9) < 1.0
    assert all(abs(x.lat_deg - KWVI_LAT) < 1e-6 for x in f)
    assert all(x.imu_healthy and x.gnss_healthy for x in f)
