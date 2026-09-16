"""Frame conventions: FRD body / NED wire → three.js world (x east, y up, z south)."""

import math

import pytest

from bridge import frames as fr


def rotate(q, v):
    """Apply quaternion (x, y, z, w) to vector v."""
    x, y, z, w = q
    vx, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx))


def close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


NOSE, RIGHT_WING, BELLY = (1, 0, 0), (0, 1, 0), (0, 0, 1)
EAST, UP, SOUTH = (1, 0, 0), (0, 1, 0), (0, 0, 1)
NORTH, DOWN, WEST = (0, 0, -1), (0, -1, 0), (-1, 0, 0)


@pytest.mark.parametrize("ypr, body, world", [
    ((0, 0, 0), NOSE, NORTH), ((0, 0, 0), RIGHT_WING, EAST), ((0, 0, 0), BELLY, DOWN),
    ((90, 0, 0), NOSE, EAST), ((180, 0, 0), NOSE, SOUTH), ((270, 0, 0), NOSE, WEST),
    ((0, 90, 0), NOSE, UP), ((0, -90, 0), NOSE, DOWN),
    ((0, 0, 90), RIGHT_WING, DOWN), ((0, 0, -90), RIGHT_WING, UP), ((0, 0, 180), BELLY, UP),
    ((90, 0, 90), RIGHT_WING, DOWN), ((90, 0, 90), NOSE, EAST),
])
def test_world_quaternion_orients_body_axes(ypr, body, world):
    q = fr.world_quaternion(*ypr)
    assert abs(math.sqrt(sum(c * c for c in q)) - 1) < 1e-12
    assert close(rotate(q, body), world), (ypr, body, rotate(q, body))


def test_quaternion_matches_matrix_for_arbitrary_attitude():
    ypr = (37.0, -52.0, 141.0)
    m = fr.body_to_world(*ypr)
    q = fr.world_quaternion(*ypr)
    for v in (NOSE, RIGHT_WING, BELLY):
        via_matrix = tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))
        assert close(rotate(q, v), via_matrix)


def test_ned_and_world_from_lla():
    origin = (36.9, -121.8, 100.0)
    n, e, d = fr.ned_from_lla(36.901, -121.8, 130.0, origin)
    assert abs(n - math.radians(0.001) * fr.EARTH_RADIUS_M) < 1e-6 and abs(e) < 1e-9 and d == -30.0
    n, e, d = fr.ned_from_lla(36.9, -121.799, 100.0, origin)
    assert abs(e - math.radians(0.001) * fr.EARTH_RADIUS_M * math.cos(math.radians(36.9))) < 1e-6 and n == 0
    assert fr.world_from_ned(100, 20, -30) == (20, 30, -100)
