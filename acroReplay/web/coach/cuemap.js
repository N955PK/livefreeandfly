// Live cue mapping: turn the detector's in-progress element into the (shape, bank) pair the tone engine consumes.
// Phase A covers lines only — a line's ideal is a fixed drawn angle, so the error is one subtraction; every other
// element returns inactive (silent) until loops (Phase B) and rolls (Phase C) are added.
//
// Conventions (see livecue.js): shape > 0 = nose high / past the target angle -> higher pitch; bank > 0 = right
// wing low -> pan right. Lines are judged on attitude, so the angle is nose elevation `el`; pan uses body `roll`
// because horizon `bank` is undefined near vertical, and roll reads a dragged wing on a vertical line directly.
import { KIND } from './detector.js';

const LINE_TARGET = { [KIND.LINE45]: 45, [KIND.LINEV]: 90 };   // magnitude of the drawn line angle, degrees

/// `cur` is the detector's current element (needs `kind` and `el0`); `f` is the latest feature (needs `el`, `roll`).
/// Returns { active, shape, bank } — active:false means there is nothing to cue, so the caller stays silent.
export function cueDrive(cur, f) {
  if (!cur || !f) return { active: false, shape: 0, bank: 0 };
  const mag = LINE_TARGET[cur.kind];
  if (mag == null || !Number.isFinite(f.el) || !Number.isFinite(f.roll)) return { active: false, shape: 0, bank: 0 };
  const target = Math.sign(cur.el0 || f.el) * mag;   // up-line (+) or down-line (-), fixed for the element
  return { active: true, shape: f.el - target, bank: f.roll };
}
