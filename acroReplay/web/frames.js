// FRD body / NED wire → three.js world (x east, y up, z south). Mirrors bridge/frames.py.
import * as THREE from 'three';

export const FT_TO_M = 0.3048;
export const EARTH_RADIUS_M = 6378137.0;
const DEG = Math.PI / 180;
const NED_TO_WORLD = [[0, 1, 0], [0, 0, -1], [-1, 0, 0]];

export function nedFromLla(lat, lon, altM, [lat0, lon0, alt0]) {
  const north = (lat - lat0) * DEG * EARTH_RADIUS_M;
  const east = (lon - lon0) * DEG * EARTH_RADIUS_M * Math.cos(lat0 * DEG);
  return [north, east, -(altM - alt0)];
}

export function worldFromNed(north, east, down) {
  return [east, -down, -north];
}

export function bodyToNed(yaw, pitch, roll) {
  const cy = Math.cos(yaw * DEG), sy = Math.sin(yaw * DEG);
  const cp = Math.cos(pitch * DEG), sp = Math.sin(pitch * DEG);
  const cr = Math.cos(roll * DEG), sr = Math.sin(roll * DEG);
  return [
    [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
    [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
    [-sp, cp * sr, cp * cr],
  ];
}

function matmul(a, b) {
  return a.map((row, i) => [0, 1, 2].map(j => row[0] * b[0][j] + row[1] * b[1][j] + row[2] * b[2][j]));
}

const m4 = new THREE.Matrix4();
export function worldQuaternion(yaw, pitch, roll, target = new THREE.Quaternion()) {
  const m = matmul(NED_TO_WORLD, bodyToNed(yaw, pitch, roll));
  m4.set(m[0][0], m[0][1], m[0][2], 0, m[1][0], m[1][1], m[1][2], 0, m[2][0], m[2][1], m[2][2], 0, 0, 0, 0, 1);
  return target.setFromRotationMatrix(m4);
}

// Session origin: first fix horizontally, at a fixed ground elevation so altitude is absolute.
export class Origin {
  constructor(groundM) { this.groundM = groundM; this.value = null; }
  update(f) {
    if (!this.value) this.value = [f.lat, f.lon, this.groundM];
  }
}

// Same shape the Python bridge sends over /ws (bridge/server.py sample_from_frame).
export function sampleFromFrame(wall, f, origin) {
  const s = {
    wall, t: f.t, init: f.init, ok: f.ok, fix: f.fix, sats: f.sats, hacc: f.hacc,
    hdg: f.hdg, pitch: f.pitch, roll: f.roll, nz: f.nz, gs: f.gs, trk: f.trk, vs: f.vs, alt: f.alt,
    rates: f.rates, pos: null, quat: null,
  };
  if (f.init && origin) {
    s.pos = worldFromNed(...nedFromLla(f.lat, f.lon, f.alt * FT_TO_M, origin));
    const q = worldQuaternion(f.hdg, f.pitch, f.roll);
    s.quat = [q.x, q.y, q.z, q.w];
  }
  return s;
}
