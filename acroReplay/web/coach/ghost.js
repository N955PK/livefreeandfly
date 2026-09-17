// The "correct figure" ghost: the 10.0 version of a graded figure, fitted to how it was actually entered —
// same entry point, entry heading snapped to the box axis when there is one, same altitude — and sized from
// the flight (quarter-one radius, first line length). Returned as a world-space polyline plus "ribs" that join
// the flown path to the ghost every second so the gap reads at a glance.
import * as THREE from 'three';
import { angleDiff } from './features.js';

const RAD = Math.PI / 180;
const KIND_LINE = 45;

/// Unit horizontal direction for a true heading in the scene frame (x east, y up, z south).
function headingDir(deg) { return new THREE.Vector3(Math.sin(deg * RAD), 0, -Math.cos(deg * RAD)); }

/// Snap a heading to the nearest box axis (0/90/180/270 from the box heading) when a box exists.
function snap(az, axisDeg) {
  if (!Number.isFinite(axisDeg)) return az;
  let best = az, bestErr = 1e9;
  for (const k of [0, 90, 180, 270]) { const a = (axisDeg + k) % 360, e = Math.abs(angleDiff(az, a)); if (e < bestErr) { bestErr = e; best = a; } }
  return bestErr <= 30 ? best : az;
}

/// Pen that draws in the vertical plane of heading `dir`: `arc(deg, radius, sense)` pitches the path up (+)
/// or down (−) by `deg` on a circle of `radius`; `line(len)` continues straight; `turn(deg, radius)` is a
/// level turn. Tracks position and flight-path angle (gamma) and heading.
class Pen {
  constructor(start, headingDeg) { this.p = start.clone(); this.hdg = headingDeg; this.gamma = 0; this.pts = [start.clone()]; }
  dirVec() { const h = headingDir(this.hdg); return new THREE.Vector3(h.x * Math.cos(this.gamma), Math.sin(this.gamma), h.z * Math.cos(this.gamma)); }
  line(len) { const n = Math.max(2, Math.ceil(len / 10)); const d = this.dirVec(); for (let i = 1; i <= n; i += 1) this.pts.push(this.p.clone().addScaledVector(d, (len * i) / n)); this.p.addScaledVector(d, len); return this; }
  arc(deg, radius, sense = 1) {
    const n = Math.max(4, Math.ceil(Math.abs(deg) / 5));
    const h = headingDir(this.hdg);
    for (let i = 1; i <= n; i += 1) {
      const g0 = this.gamma, g1 = this.gamma + (sense * deg * RAD) / n;
      // chord along the local direction, integrated on the circle
      const ds = radius * Math.abs(g1 - g0);
      const gm = (g0 + g1) / 2;
      this.p.add(new THREE.Vector3(h.x * Math.cos(gm) * ds, Math.sin(gm) * ds, h.z * Math.cos(gm) * ds));
      this.gamma = g1;
      this.pts.push(this.p.clone());
    }
    // Past vertical the ghost is flying "backwards" along the heading: normalise gamma into (−180, 180] and flip.
    if (this.gamma > Math.PI / 2 + 1e-6 || this.gamma < -Math.PI / 2 - 1e-6) {
      this.gamma = Math.PI - this.gamma; if (this.gamma > Math.PI) this.gamma -= 2 * Math.PI;
      this.hdg = (this.hdg + 180) % 360;
    }
    return this;
  }
  turn(deg, radius) {
    const n = Math.max(6, Math.ceil(Math.abs(deg) / 5));
    for (let i = 1; i <= n; i += 1) {
      const dh = deg / n;
      const hm = this.hdg + dh / 2;
      this.p.addScaledVector(headingDir(hm), radius * Math.abs(dh) * RAD);
      this.hdg = (this.hdg + dh + 360) % 360;
      this.pts.push(this.p.clone());
    }
    return this;
  }
}

/// Length flown along an element (metres) from its 25 Hz samples.
function elLength(e) { const s = e?.samples || []; let d = 0; for (let i = 1; i < s.length; i += 1) d += s[i].tas * (s[i].t - s[i - 1].t); return d; }

/// Build the ghost for a graded figure. `entryPos` is the flown world position at the figure start,
/// `entryAz` the flown entry heading, `flown` the flown samples with world positions (for ribs).
export function idealFigure(grade, m, entryPos, entryAz, flown, ctx = {}) {
  const hdg = snap(entryAz, ctx.axisDeg);
  const pen = new Pen(entryPos, hdg);
  const r0 = (arr, fallback) => (arr && Number.isFinite(arr[0]) && arr[0] > 20 ? arr[0] : fallback);
  switch (grade.type) {
    case 'loop': {
      const R = r0(grade.measurements.radii, 120);
      pen.line(20).arc(360, R, 1).line(30);
      break;
    }
    case 'half cuban': {
      const R = r0(grade.measurements.radii, 120);
      const lineLen = Math.max(60, (grade.measurements.lineBeforeM + grade.measurements.lineAfterM) * 1.15 + 40);
      const rExit = Math.max(40, elLength(m.exitPull) / (45 * RAD) || R);
      pen.line(20).arc(225, R, 1);            // ⅝ loop to 45° down inverted
      pen.line(lineLen);                       // 45° down line with the roll centred (straight path)
      pen.arc(45, rExit, 1).line(30);          // ⅛ pull to level on the reciprocal heading
      break;
    }
    case '45 up line': {
      const rIn = Math.max(40, elLength(m.els?.find((e) => e.kind === 'loop' && e.qMean > 0)) / (45 * RAD) || 100);
      const len = Math.max(80, elLength(m.line) || 200);
      pen.line(20).arc(45, rIn, 1).line(len).arc(45, rIn, -1).line(30);
      break;
    }
    case 'slow roll': {
      pen.line(Math.max(150, elLength(m.roll) + 60));
      break;
    }
    case '180 turn': {
      const arcLen = elLength(m.turn) || 400;
      const R = arcLen / Math.PI;
      const sense = Math.sign(m.turn.dAz) || 1;
      pen.line(20).turn(180 * sense, R).line(30);
      break;
    }
    case 'spin': {
      // The exit direction follows the rotation: N turns leave the nose (N mod 1)\u00d7360\u00b0 round from entry, so a
      // 1\u00bd-turn spin flies out reversed 180\u00b0, a 1-turn spin flies out the way it came in. Drawn as the entry line,
      // a vertical autorotating descent, then a quarter-loop pull-out onto that recovery heading.
      const turns = ctx.spinTurns ?? grade.measurements?.want ?? 1.5;
      const sense = (grade.measurements?.iUpDeg || 0) < 0 ? -1 : 1;   // which way the nose went round
      const exitOffset = ((turns * 360) % 360) * sense;
      const drop = Math.max(60, Math.abs(m.spin.dAlt || 0) * 0.3048);
      const rOut = Math.max(40, elLength(m.pull) / (90 * RAD) || 100);
      pen.line(15).arc(-90, 25, 1).line(drop);
      pen.hdg = (pen.hdg + exitOffset + 360) % 360;
      pen.arc(90, rOut, 1).line(30);
      break;
    }
    default: return null;
  }
  const points = pen.pts;
  // Ribs: from the flown path to the nearest ghost point, once per second.
  const ribs = [];
  let lastT = -1e9;
  for (const s of flown) {
    if (!s.v || s.t - lastT < 1) continue;
    lastT = s.t;
    let best = null, bestD = Infinity;
    for (const g of points) { const d = g.distanceToSquared(s.v); if (d < bestD) { bestD = d; best = g; } }
    if (best) ribs.push([s.v.clone(), best.clone()]);
  }
  return { points, ribs };
}
