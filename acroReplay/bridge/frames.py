"""Frame conventions between the wire and the screen.

The Hub reports attitude as yaw/pitch/roll of a front-right-down (FRD) body frame
relative to north-east-down (NED). three.js renders in a right-handed frame with
x = east, y = up, z = south. Everything the renderer needs is computed here so
the browser does no frame math at all.
"""

import math

EARTH_RADIUS_M = 6378137.0
FT_TO_M = 0.3048
KT_TO_MPS = 0.514444

_NED_TO_WORLD = ((0.0, 1.0, 0.0), (0.0, 0.0, -1.0), (-1.0, 0.0, 0.0))


def ned_from_lla(lat_deg, lon_deg, alt_m, origin):
    """Flat-earth north/east/down (m) of a point relative to ``origin = (lat_deg, lon_deg, alt_m)``.

    Accurate to well under a metre across an aerobatic box.
    """
    lat0, lon0, alt0 = origin
    north = math.radians(lat_deg - lat0) * EARTH_RADIUS_M
    east = math.radians(lon_deg - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    return north, east, -(alt_m - alt0)


def world_from_ned(north, east, down):
    """three.js world coordinates (x east, y up, z south) of a NED vector."""
    return east, -down, -north


def body_to_ned(yaw_deg, pitch_deg, roll_deg):
    """Rotation matrix taking FRD body vectors to NED (yaw about z, then pitch about y, then roll about x)."""
    cy, sy = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    cp, sp = math.cos(math.radians(pitch_deg)), math.sin(math.radians(pitch_deg))
    cr, sr = math.cos(math.radians(roll_deg)), math.sin(math.radians(roll_deg))
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def _matmul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def body_to_world(yaw_deg, pitch_deg, roll_deg):
    """Rotation matrix taking FRD body vectors straight to three.js world coordinates."""
    return _matmul(_NED_TO_WORLD, body_to_ned(yaw_deg, pitch_deg, roll_deg))


def quaternion_from_matrix(m):
    """Unit quaternion ``(x, y, z, w)`` — three.js component order — of a proper rotation matrix."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        return (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, 0.25 * s
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        return 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s
    if m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        return (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s
    s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
    return (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s


def world_quaternion(yaw_deg, pitch_deg, roll_deg):
    """Quaternion ``(x, y, z, w)`` that orients an FRD-built aircraft model in the three.js world."""
    return quaternion_from_matrix(body_to_world(yaw_deg, pitch_deg, roll_deg))
