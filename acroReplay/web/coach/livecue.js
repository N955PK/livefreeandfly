// Live guidance tone: sonify the pilot's deviation from the ideal shape during a figure. Pitch tracks the signed
// shape error (±2 octaves), stereo pan tracks the low/dragging wing, blip cadence tracks the SHAPE error only (a
// wing drag pans but never quickens), silent within a deadband. Mapping validated in prototypes/livecue.html.
const CENTER = 440;        // Hz, the on-shape centre pitch
const SHAPE_SPAN = 30;     // degrees of shape error mapped to full scale
const BANK_SPAN = 45;      // degrees of bank mapped to a full pan
const PITCH_OCT = 2;       // octaves of pitch swing over the shape span
const SLOW = 1.2;          // blip rate at the deadband edge (beeps/s)
const FAST = 20;           // blip rate at full shape error
const DEADBAND = 3;        // shape-degrees of tolerance before any sound
const MAX_GAIN = 1.6;      // volume ceiling — a cockpit headset needs headroom, so this runs hot on purpose

const clamp01 = (x) => Math.max(0, Math.min(1, x));

export class LiveCue {
  constructor() {
    this.mode = 'off';        // 'off' | 'constant' | 'blip'
    this.volume = 0.7;        // 0..1 slider
    this.cur = { shape: 0, bank: 0 };
    this.ctx = null;
    this.blipTimer = null;
    this.testing = false;     // while a Test sample plays, the per-frame live driver leaves the engine alone
  }

  setMode(mode) {
    this.mode = mode;
    if (mode === 'off') { this.silence(); return; }
    this.ensure();
    this.apply();
  }

  setVolume(v) {
    this.volume = clamp01(v);
    if (this.master) this.master.gain.value = this._masterGain();
  }

  _masterGain() { return Math.pow(this.volume, 1.3) * MAX_GAIN; }

  ensure() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return; }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    this.ctx = new Ctx();
    this.osc = this.ctx.createOscillator(); this.osc.type = 'sine'; this.osc.frequency.value = CENTER;
    this.env = this.ctx.createGain(); this.env.gain.value = 0;    // steady-tone envelope (constant mode)
    this.pan = this.ctx.createStereoPanner();
    this.comp = this.ctx.createDynamicsCompressor();              // tame peaks when the volume runs hot
    this.master = this.ctx.createGain(); this.master.gain.value = this._masterGain();
    this.osc.connect(this.env).connect(this.pan).connect(this.comp).connect(this.master).connect(this.ctx.destination);
    this.osc.start();
  }

  silence() {
    if (this.env && this.ctx) this.env.gain.setTargetAtTime(0, this.ctx.currentTime, 0.03);
    if (this.blipTimer) { clearTimeout(this.blipTimer); this.blipTimer = null; }
  }

  /// Per-frame drive. shape: signed shape error in degrees (+ = ballooning / nose-high / past-vertical);
  /// bank: signed bank in degrees (+ = right wing low). Call at the sample rate while a figure is being flown.
  update(shape, bank) {
    this.cur = { shape, bank };
    if (this.ctx && this.mode !== 'off') this.apply();
  }

  _terms() {
    const { shape, bank } = this.cur;
    const shapeNorm = clamp01(Math.abs(shape) / SHAPE_SPAN);
    const bankNorm = clamp01(Math.abs(bank) / BANK_SPAN);
    const norm = Math.max(shapeNorm, bankNorm);
    const deadNorm = clamp01(DEADBAND / SHAPE_SPAN);
    const denom = Math.max(1e-6, 1 - deadNorm);
    return {
      freq: CENTER * Math.pow(2, PITCH_OCT * shape / SHAPE_SPAN),
      pan: Math.max(-1, Math.min(1, bank / BANK_SPAN)),
      drive: clamp01((norm - deadNorm) / denom),           // combined — loudness / audibility
      shapeDrive: clamp01((shapeNorm - deadNorm) / denom),  // shape only — blip cadence
    };
  }

  apply() {
    if (!this.ctx || this.mode === 'off') { this.silence(); return; }
    const { freq, pan, drive } = this._terms();
    const t = this.ctx.currentTime;
    this.osc.frequency.setTargetAtTime(freq, t, 0.04);
    this.pan.pan.setTargetAtTime(pan, t, 0.04);
    if (this.mode === 'constant') {
      if (this.blipTimer) { clearTimeout(this.blipTimer); this.blipTimer = null; }
      this.env.gain.setTargetAtTime(drive, t, 0.045);
    } else {                                   // blip
      this.env.gain.setTargetAtTime(0, t, 0.03);
      if (!this.blipTimer) this._blipLoop();
    }
  }

  _blipLoop() {
    const tick = () => {
      this.blipTimer = null;
      if (!this.ctx || this.mode !== 'blip') return;
      const { freq, pan, drive, shapeDrive } = this._terms();
      if (drive > 0) this._blip(freq, pan, drive);
      const rate = drive > 0 ? (SLOW + (FAST - SLOW) * shapeDrive) : 6;   // poll a few times a second while silent
      this.blipTimer = setTimeout(tick, 1000 / rate);
    };
    tick();
  }

  _blip(freq, pan, drive) {
    const t = this.ctx.currentTime;
    const o = this.ctx.createOscillator(); o.type = 'triangle'; o.frequency.value = freq;
    const g = this.ctx.createGain(); g.gain.setValueAtTime(0.0001, t);
    const p = this.ctx.createStereoPanner(); p.pan.value = pan;
    o.connect(g).connect(p).connect(this.comp);
    const peak = 0.4 + 0.6 * drive;
    g.gain.linearRampToValueAtTime(peak, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
    o.start(t); o.stop(t + 0.1);
  }

  /// A ~2.5 s mid-level example so the pilot can set the volume by ear. Uses the chosen mode (or a steady tone if
  /// Off), at a mid balloon with wings level.
  test() {
    this.ensure();
    if (!this.ctx) return;
    this.testing = true;
    const wasOff = this.mode === 'off';
    if (wasOff) this.mode = 'constant';   // preview Off as a steady tone; otherwise keep the live mode
    this.cur = { shape: SHAPE_SPAN * 0.55, bank: 0 };   // mid balloon, mid cadence, centred
    this.apply();
    clearTimeout(this._testStop);
    this._testStop = setTimeout(() => {
      this.testing = false;
      this.cur = { shape: 0, bank: 0 };
      // Don't restore a snapshotted mode — read the mode as it is now, so switching Constant/Blip mid-test can't
      // revert it (that desync is what made Constant sometimes emit blips).
      if (wasOff) { this.mode = 'off'; this.silence(); } else this.apply();
    }, 2500);
  }
}
