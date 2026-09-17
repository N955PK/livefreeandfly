// Per-sample quantities the detector and the scorer work from, derived once from a live/replayed sample.
// Attitude comes from the world quaternion so nothing breaks at ±90° pitch; the flight path from GPS.
import * as THREE from 'three';

const RAD = 180 / Math.PI;
const KT_TO_MPS = 0.514444;
const FPM_TO_MPS = 0.00508;
const nose = new THREE.Vector3();
const right = new THREE.Vector3();
const q = new THREE.Quaternion();

/// `s` is a sample with hdg/pitch/roll/nz/gs/trk/vs/alt/rates and quat [x,y,z,w].
/// Returns { t, el, az, bank, fpa, trk, gs, tas, p, q, r, nz, alt, inverted }.
export function features(s) {
  q.set(s.quat[0], s.quat[1], s.quat[2], s.quat[3]);
  nose.set(1, 0, 0).applyQuaternion(q);      // body x → world (x east, y up, z south)
  right.set(0, 1, 0).applyQuaternion(q);     // body y (right wing)
  const el = Math.asin(THREE.MathUtils.clamp(nose.y, -1, 1)) * RAD;          // nose elevation above the horizon
  const az = ((Math.atan2(nose.x, -nose.z) * RAD) + 360) % 360;              // nose azimuth, degrees true
  // Bank as the judge sees it: the right wing's dip below the horizon; near-vertical noses make it meaningless.
  const bank = Math.abs(el) < 80 ? Math.atan2(-right.y, Math.hypot(right.x, right.z)) * RAD * Math.sign(1) : NaN;
  const gs = s.gs * KT_TO_MPS;
  const vs = s.vs * FPM_TO_MPS;
  const fpa = Number.isFinite(s.fpa) ? s.fpa : Math.atan2(vs, Math.max(gs, 0.1)) * RAD;
  return {
    t: s.t, el, az, bank, fpa, trk: s.trk, gs, tas: Math.hypot(gs, vs),
    p: s.rates[0], q: s.rates[1], r: s.rates[2], nz: s.nz, alt: s.alt,
    inverted: Number.isFinite(bank) && Math.abs(bank) > 135,
    roll: s.roll, hdg: s.hdg,
  };
}

/// Signed smallest difference a − b in degrees, in (−180, 180].
export function angleDiff(a, b) {
  let d = (a - b) % 360;
  if (d > 180) d -= 360;
  if (d <= -180) d += 360;
  return d;
}
