// The wing rock: the pilot signals the start (and, in competition, the end) of a routine by rocking the wings —
// three bank pulses to the SAME side, each past ~45°, each returning to level, within a few seconds. Same-side
// (not alternating) is the discriminator: a roll goes round without returning to level, a Dutch-roll wobble
// alternates, a turn holds the bank. The rock is often flown in the dive/climb used to set up, so pitch is not
// used. Validated against data16 (three entry rocks at ~402/653/949 s, left, ~50-67°, no false hits on rolls).
const PEAK = 45;      // a pulse must bank at least this far past level (deg)
const CEIL = 110;     // ...but not go round like a roll (a roll's |bank| peaks near 180)
const RESET = 18;     // the pulse ends when the wings come back within this of level
const SPAN = 5.5;     // the three pulses must land inside this window (s)
const NEED = 3;
const COOLDOWN = 4.0;   // after a rock, ignore further rocks for this long so one rocking episode fires once

export class WingRockDetector {
  constructor(onRock) {
    this.onRock = onRock;   // called {t, dir} when a rock completes (dir: -1 left, +1 right)
    this.reset();
  }

  reset() { this.inPulse = false; this.peak = 0; this.peakT = 0; this.pulses = []; this.lastRockT = -1e9; }

  /// Feed one per-sample feature object (needs `roll`, the signed bank in degrees, and `t`).
  push(f) {
    const b = f.roll;
    if (!Number.isFinite(b)) return false;
    if (f.t - this.lastRockT < COOLDOWN) { this.inPulse = false; this.pulses = []; return false; }   // refractory
    if (!this.inPulse) {
      if (Math.abs(b) >= PEAK) { this.inPulse = true; this.peak = b; this.peakT = f.t; }
      return false;
    }
    if (Math.abs(b) > Math.abs(this.peak)) { this.peak = b; this.peakT = f.t; }
    if (Math.abs(b) >= RESET) return false;   // still banked; the pulse has not closed yet

    // The wings came back to level: the pulse has closed.
    this.inPulse = false;
    const mag = Math.abs(this.peak);
    if (mag < PEAK || mag > CEIL) { this.pulses = []; return false; }   // a roll or noise, not a rock pulse
    this.pulses.push({ t: this.peakT, sign: Math.sign(this.peak) });
    this.pulses = this.pulses.filter((p) => this.peakT - p.t <= SPAN);   // keep only the recent window
    const recent = this.pulses.slice(-NEED);
    if (recent.length === NEED && recent.every((p) => p.sign === recent[0].sign)
        && recent[NEED - 1].t - recent[0].t <= SPAN) {
      this.pulses = [];
      this.lastRockT = f.t;
      this.onRock({ t: f.t, dir: recent[0].sign });
      return true;
    }
    return false;
  }
}
