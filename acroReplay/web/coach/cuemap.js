// Live cue mapping: turn the detector's in-progress element into the (shape, bank) pair the tone engine consumes.
// Conventions (see livecue.js): shape > 0 = nose high / ballooning / past the target -> higher pitch; bank > 0 =
// right wing low -> pan right; both zero -> the engine's deadband keeps it silent.
//
//   Lines  (LINE45/LINEV): judged on attitude, so shape = nose elevation minus the drawn line angle (±45/±90 by
//                          element kind and entry sign); pan = body roll (horizon bank is undefined near vertical,
//                          and roll reads a dragged wing on a vertical line directly).
//   Loops  (LOOP):         roundness. Instantaneous radius R = TAS / pitch-rate; the target R* is the median R over
//                          the first quadrant (until |iq| passes 90°), silent until then; shape is the normalised
//                          radius error (pinch = low, balloon = high); pan = horizon bank on the sides, roll near
//                          the vertical top/bottom.
//   Rolls  (ROLL):         bank sweeps by design, so pitch-only: shape = flight-path sag from the roll's entry
//                          attitude (nose drop reads low), no pan. Spins need nothing extra — the recovery down-line
//                          is a LINEV and is cued as one.
import { KIND } from './detector.js';

const SHAPE_FS = 30;      // full-scale shape, degrees — matches livecue's SHAPE_SPAN
const RADIUS_TOL = 0.4;   // fractional radius error mapped to full-scale shape (tuned in the air)
const MIN_OMEGA = 0.12;   // rad/s — floor on pitch rate so R = TAS/ω can't blow up at a loop's transitions
const R_MIN = 25;         // m — plausible loop-radius band; readings outside are q→0 noise, kept out of the median
const R_MAX = 2000;

const INACTIVE = { active: false, shape: 0, bank: 0 };
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
function median(a) {
  const s = [...a].sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export class LiveCueMap {
  constructor() { this.cur = null; this.st = null; }

  /// `cur` is the detector's current element (needs `kind`, `el0`, `iq`); `f` is the latest feature
  /// (needs `el`, `roll`, `q`, `tas`, `bank`). Returns { active, shape, bank } — active:false means stay silent.
  drive(cur, f) {
    if (!cur || !f) { this.cur = null; return INACTIVE; }
    if (cur !== this.cur) { this.cur = cur; this.st = { rs: [], rStar: null }; }   // new element -> fresh state
    let d;
    switch (cur.kind) {
      case KIND.LINE45: d = this._line(cur, f, 45); break;
      case KIND.LINEV: d = this._line(cur, f, 90); break;
      case KIND.LOOP: d = this._loop(cur, f); break;
      case KIND.ROLL: d = this._roll(cur, f); break;
      default: return INACTIVE;   // level / turn / spin / pivot / other -> nothing to cue
    }
    if (d.active) d.shape = clamp(d.shape, -SHAPE_FS, SHAPE_FS);   // keep pitch inside the engine's ±2-octave range
    return d;
  }

  _line(cur, f, mag) {
    if (!Number.isFinite(f.el) || !Number.isFinite(f.roll)) return INACTIVE;
    const target = Math.sign(cur.el0 || f.el) * mag;   // up-line (+) or down-line (-), fixed for the element
    return { active: true, shape: f.el - target, bank: f.roll };
  }

  _loop(cur, f) {
    const omega = Math.abs(f.q) * Math.PI / 180;
    if (!(omega > MIN_OMEGA) || !Number.isFinite(f.tas)) return INACTIVE;
    const r = f.tas / omega;
    const st = this.st;
    if (st.rStar == null) {                            // still setting the target over the first quadrant
      if (r >= R_MIN && r <= R_MAX) st.rs.push(r);
      if (Math.abs(cur.iq) >= 90 && st.rs.length) st.rStar = median(st.rs);
      return INACTIVE;                                 // silent until the loop's size is known
    }
    const shape = clamp(SHAPE_FS * (r / st.rStar - 1) / RADIUS_TOL, -SHAPE_FS, SHAPE_FS);
    const bank = Number.isFinite(f.bank) ? f.bank : f.roll;   // horizon bank on the sides, roll at top/bottom
    return { active: true, shape, bank };
  }

  _roll(cur, f) {
    if (!Number.isFinite(f.el) || !Number.isFinite(cur.el0)) return INACTIVE;
    return { active: true, shape: f.el - cur.el0, bank: 0 };   // nose-drop sag from entry attitude, no pan
  }
}
