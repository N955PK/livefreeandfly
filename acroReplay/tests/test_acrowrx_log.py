"""ACROWRX SD-log reader against a scrubbed 40-record slice of a real flight (tests/fixtures/mini.acrowrx)."""

from pathlib import Path

from onflight.acrowrx_log import AW_LEN, iter_blocks, read_log, to_udp_frame
from onflight.udp_ins import INS_SIZE, decode_ins

FIXTURE = Path(__file__).parent / "fixtures" / "mini.acrowrx"
KWVI_LAT, KWVI_LON = 36.93575, -121.78975


def test_blocks_parse_and_checksums_verify():
    blocks = list(iter_blocks(FIXTURE.read_bytes()))
    assert [b.tag for b in blocks[:2]] == [b"MD", b"AW"] and len(blocks) == 41
    assert all(b.checksum_ok for b in blocks)
    assert all(len(b.payload) == AW_LEN for b in blocks if b.tag == b"AW")


def test_records_decode_to_physical_values():
    identity, config, recs = read_log(FIXTURE)
    assert (identity.tail_number, identity.pilot_name, identity.aircraft_type) == ("N12345", "Test Pilot", "TEST")
    assert len(recs) == 40 and all(r.ins_initialized for r in recs)
    r = recs[0]
    assert abs(r.lat_deg - KWVI_LAT) < 1e-6 and abs(r.gnss_lon_deg - KWVI_LON) < 1e-6
    assert -90 <= r.pitch_deg <= 90 and -180 <= r.roll_deg <= 180 and 0 <= r.true_heading_deg < 360
    assert abs(((r.true_heading_deg - r.mag_heading_deg) % 360) - r.mag_declination_deg) < 0.02
    assert abs(r.mag_declination_deg - 12.5) < 0.3
    assert r.gnss_fix in (3, 4) and 6 <= r.gnss_num_sv <= 30
    assert r.utc.year == 2026 and 3.0 < r.input_voltage_v < 6.5
    assert 0.2 < sum(a * a for a in r.accel_g) ** 0.5 < 6
    assert 40 < sum(m * m for m in r.mag_ut) ** 0.5 < 60
    assert 80_000 < r.static_pres_pa < 102_000
    dt = [b.sys_time_s - a.sys_time_s for a, b in zip(recs, recs[1:])]
    assert all(abs(x - 0.02) < 0.002 for x in dt)


def test_udp_frame_round_trip_matches_record():
    _, _, recs = read_log(FIXTURE)
    for r in recs[:5]:
        frame = to_udp_frame(r)
        assert len(frame) == INS_SIZE
        f = decode_ins(frame)
        assert f.ins_initialized and abs(f.pitch_deg - r.pitch_deg) < 0.011 and abs(f.roll_deg - r.roll_deg) < 0.011
        assert abs(f.true_heading_deg - r.true_heading_deg) < 0.011 and abs(f.lat_deg - r.lat_deg) < 1e-7
        assert f.alt_msl_ft == round(r.pres_alt_ft) and abs(f.sys_time_s - r.sys_time_s) < 0.001
        assert (f.p_dps, f.q_dps, f.r_dps) == r.gyro_dps and f.utc == r.utc
