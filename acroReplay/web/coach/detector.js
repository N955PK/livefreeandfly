// Element detector: turns the 50 Hz feature stream into a sequence of aerobatic elements (the pieces every
// figure is built from — level flight, lines, looping segments, rolls, turns, spins, hammerhead pivots) and
// groups them into figures: everything between two stretches of level flight.
//
// Thresholds were set on data16 (Christen Eagle): loops pull 12–45 °/s of pitch rate, slow rolls run
// 100–150 °/s, the hammerhead pivot yaws 40–70 °/s below 25 kt. The Hub's gyros are low-passed at 3 Hz,
// so peaks read ~10 % low — thresholds sit well under the real rates.
import { features, angleDiff } from './features.js';

export const KIND = {
  LEVEL: 'level', LINE45: 'line45', LINEV: 'linev', LOOP: 'loop', ROLL: 'roll', TURN: 'turn',
  SPIN: 'spin', PIVOT: 'pivot', OTHER: 'other',
};

// Minimum dwell (s) before a new raw label takes over; shorter blips stay with the current element.
const DWELL = { level: 0.6, line45: 0.4, linev: 0.3, loop: 0.3, roll: 0.16, turn: 0.8, spin: 0.5, pivot: 0.3, other: 0.3 };
const LEVEL_TO_CLOSE_S = 1.0;     // level flight this long ends a figure
const MIN_FIGURE_S = 2.0;

function rawKind(f, prev) {
  const ap = Math.abs(f.p), aq = Math.abs(f.q), ar = Math.abs(f.r);
  const slow = f.gs < 23;   // m/s ≈ 45 kt
  if (ar >= 40 && f.el < -20 && f.gs < 36 && f.nz < 1.6) return KIND.SPIN;               // autorotation, nose down
  if (slow && ar >= 25 && Math.abs(f.el) > 40) return KIND.PIVOT;                        // hammerhead turnaround
  if (ap >= 45) return KIND.ROLL;
  // A steep level turn is mostly body pitch rate, so the turn test comes before the looping test.
  if (Number.isFinite(f.bank) && Math.abs(f.bank) >= 45 && Math.abs(f.fpa) < 20 && Math.abs(f.el) < 25) return KIND.TURN;
  if (aq >= 12) return KIND.LOOP;
  if (Math.abs(f.el) >= 72) return KIND.LINEV;
  if (Math.abs(Math.abs(f.el) - 45) <= 14) return KIND.LINE45;
  if (Number.isFinite(f.bank) && Math.abs(f.bank) < 20 && Math.abs(f.el) < 14 && Math.abs(f.fpa) < 12 && aq < 10 && ap < 25) return KIND.LEVEL;
  // Inverted level (bank ~180) counts as level for figure boundaries too.
  if (Number.isFinite(f.bank) && Math.abs(f.bank) > 160 && Math.abs(f.el) < 14 && aq < 10 && ap < 25) return KIND.LEVEL;
  return prev === KIND.LEVEL ? KIND.OTHER : (prev || KIND.OTHER);
}

function newElement(kind, f) {
  return {
    kind, t0: f.t, t1: f.t, n: 0,
    ip: 0, iq: 0, ir: 0,              // integrated body rates, degrees
    alt0: f.alt, alt1: f.alt, altMin: f.alt, altMax: f.alt,
    nzMin: f.nz, nzMax: f.nz,
    az0: f.az, az1: f.az, dAz: 0,     // nose azimuth change, unwrapped
    trk0: f.trk, trk1: f.trk,
    el0: f.el, el1: f.el, elSum: 0, elSq: 0,
    bank0: f.bank, bankSum: 0, bankN: 0,
    gs0: f.gs, gs1: f.gs, gsMin: f.gs, gsMax: f.gs,
    pSum: 0, pSq: 0, qSum: 0, qSq: 0,
    inverted0: f.inverted, inverted1: f.inverted,
    samples: [],                      // features kept for the scorer (decimated to 25 Hz)
  };
}

function accumulate(e, f, dt, prevF) {
  e.t1 = f.t; e.n += 1;
  e.ip += f.p * dt; e.iq += f.q * dt; e.ir += f.r * dt;
  e.alt1 = f.alt; e.altMin = Math.min(e.altMin, f.alt); e.altMax = Math.max(e.altMax, f.alt);
  e.nzMin = Math.min(e.nzMin, f.nz); e.nzMax = Math.max(e.nzMax, f.nz);
  if (prevF) e.dAz += angleDiff(f.az, prevF.az);
  e.az1 = f.az; e.trk1 = f.trk;
  e.el1 = f.el; e.elSum += f.el; e.elSq += f.el * f.el;
  if (Number.isFinite(f.bank)) { e.bankSum += f.bank; e.bankN += 1; }
  e.gs1 = f.gs; e.gsMin = Math.min(e.gsMin, f.gs); e.gsMax = Math.max(e.gsMax, f.gs);
  e.pSum += f.p; e.pSq += f.p * f.p; e.qSum += f.q; e.qSq += f.q * f.q;
  e.inverted1 = f.inverted;
  if (e.n % 2 === 0) e.samples.push(f);
}

export function elementSummary(e) {
  const n = Math.max(1, e.n);
  const elMean = e.elSum / n, elStd = Math.sqrt(Math.max(0, e.elSq / n - elMean * elMean));
  const pMean = e.pSum / n, pStd = Math.sqrt(Math.max(0, e.pSq / n - pMean * pMean));
  const qMean = e.qSum / n, qStd = Math.sqrt(Math.max(0, e.qSq / n - qMean * qMean));
  return {
    kind: e.kind, t0: e.t0, t1: e.t1, dur: e.t1 - e.t0,
    ip: e.ip, iq: e.iq, ir: e.ir, dAz: e.dAz, dAlt: e.alt1 - e.alt0, altMin: e.altMin, altMax: e.altMax,
    nzMin: e.nzMin, nzMax: e.nzMax, elMean, elStd, el0: e.el0, el1: e.el1,
    bankMean: e.bankN ? e.bankSum / e.bankN : NaN, gs0: e.gs0, gs1: e.gs1, gsMin: e.gsMin, gsMax: e.gsMax,
    pMean, pStd, qMean, qStd, inverted0: e.inverted0, inverted1: e.inverted1,
    trk0: e.trk0, trk1: e.trk1, az0: e.az0, az1: e.az1,
  };
}

// A hammerhead's turnaround looks like a spin to the per-sample rules (nose down, yawing, slow), and the
// torque and pitch fragments around it come out as short rolls. Everything from the first slow yaw (and any
// slow fragments just before it) to the down line is one PIVOT.
function mergePivot(body) {
  const yaw = body.findIndex((e) => e.kind === KIND.PIVOT || (e.kind === KIND.SPIN && e.gsMax < 30));
  if (yaw < 0) return body;
  let start = yaw;
  while (start > 0 && [KIND.ROLL, KIND.OTHER].includes(body[start - 1].kind) && body[start - 1].gsMin < 30) start -= 1;
  let down = body.findIndex((e, i) => i > yaw && e.kind === KIND.LINEV && e.elMean < -40);
  if (down < 0) down = body.findIndex((e, i) => i > yaw && e.kind === KIND.LOOP && e.qMean > 0);
  if (down < 0) return body;
  const parts = body.slice(start, down);
  const sum = (k) => parts.reduce((a, e) => a + e[k], 0);
  const merged = {
    ...parts[0], kind: KIND.PIVOT, t0: parts[0].t0, t1: parts[parts.length - 1].t1,
    ip: sum('ip'), iq: sum('iq'), ir: sum('ir'), dAz: sum('dAz'),
    altMin: Math.min(...parts.map((e) => e.altMin)), altMax: Math.max(...parts.map((e) => e.altMax)),
    nzMin: Math.min(...parts.map((e) => e.nzMin)), nzMax: Math.max(...parts.map((e) => e.nzMax)),
    gsMin: Math.min(...parts.map((e) => e.gsMin)), gsMax: Math.max(...parts.map((e) => e.gsMax)),
    el0: parts[0].el0, el1: parts[parts.length - 1].el1,
  };
  merged.dAlt = parts[parts.length - 1].altMin - parts[0].altMax;
  merged.dur = merged.t1 - merged.t0;
  return [...body.slice(0, start), merged, ...body.slice(down)];
}

export class Detector {
  constructor(onFigure) {
    this.onFigure = onFigure;
    this.reset();
  }

  reset() {
    this.kind = KIND.LEVEL;
    this.current = null;
    this.pending = null;              // { kind, t0, frames } — a candidate new label waiting out its dwell
    this.elements = [];               // closed elements of the figure in progress
    this.figureOpen = false;
    this.prevF = null;
    this.lastLevelStart = null;
    this.figures = [];
  }

  push(sample) {
    const f = features(sample);
    if (!Number.isFinite(f.t)) return null;
    const prevF = this.prevF;
    const dt = prevF ? Math.min(0.1, Math.max(0, f.t - prevF.t)) : 0.02;
    if (prevF && f.t < prevF.t - 1) this.reset();   // replay wrapped or the file restarted
    if (!this.current) this.current = newElement(this.kind, f);

    const raw = rawKind(f, this.kind);
    let switched = false;
    if (raw !== this.kind) {
      if (!this.pending || this.pending.kind !== raw) this.pending = { kind: raw, t0: f.t, frames: [] };
      this.pending.frames.push(f);
      if (f.t - this.pending.t0 >= DWELL[raw]) {
        // Re-attribute the pending frames to the new element.
        this.closeElement(this.pending.frames[0]);
        this.kind = raw;
        this.current = newElement(raw, this.pending.frames[0]);
        let pf = this.pending.frames[0];
        for (const g of this.pending.frames.slice(1)) { accumulate(this.current, g, Math.min(0.1, g.t - pf.t), pf); pf = g; }
        this.pending = null;
        switched = true;
      }
    } else {
      this.pending = null;
    }
    if (!switched) accumulate(this.current, f, dt, prevF);
    this.prevF = f;

    // Figure bookkeeping: a figure opens when we leave level flight, closes after LEVEL_TO_CLOSE_S of level.
    let figure = null;
    if (this.kind === KIND.LEVEL) {
      if (this.figureOpen && f.t - this.current.t0 >= LEVEL_TO_CLOSE_S) figure = this.closeFigure();
    } else if (!this.figureOpen) {
      this.figureOpen = true;
      this.figureStart = this.current.t0;
    }
    return figure;
  }

  closeElement(untilF) {
    const e = this.current;
    if (!e) return;
    if (untilF) e.t1 = untilF.t;
    if (this.figureOpen || e.kind !== KIND.LEVEL) this.elements.push(elementSummary(e));
    else this.elements = [elementSummary(e)];   // keep the last level line as the entry line
  }

  closeFigure() {
    const els = this.elements.filter((e) => e.kind !== KIND.LEVEL || e.t0 < this.figureStart);
    const body = this.elements.filter((e) => e.kind !== KIND.LEVEL);
    this.elements = [];
    this.figureOpen = false;
    // Ordinary flying (gentle turns, climbs, descents) only produces OTHER; a figure needs a real element.
    if (!body.some((e) => e.kind !== KIND.OTHER)) return null;
    const elements = mergePivot(body);
    const t0 = elements[0].t0, t1 = elements[elements.length - 1].t1;
    if (t1 - t0 < MIN_FIGURE_S) return null;
    const figure = { t0, t1, dur: t1 - t0, elements, entry: els.find((e) => e.kind === KIND.LEVEL) || null };
    figure.exitAz = this.current ? this.current.az0 : NaN;
    this.figures.push(figure);
    if (this.onFigure) this.onFigure(figure);
    return figure;
  }

  /// Convenience for whole-flight analysis.
  static run(samples) {
    const d = new Detector();
    for (const s of samples) if (s.init && s.quat) d.push(s);
    return d.figures;
  }
}

/// Short human tag for an element, for timelines and logs.
export function describe(e) {
  const deg = (v) => `${Math.round(v)}°`;
  switch (e.kind) {
    case KIND.LOOP: return `${e.qMean >= 0 ? 'pull' : 'push'} ${deg(Math.abs(e.iq))}`;
    case KIND.ROLL: return `roll ${deg(Math.abs(e.ip))}`;
    case KIND.LINE45: return `45${e.elMean > 0 ? '↑' : '↓'} ${e.dur.toFixed(1)}s${e.inverted0 ? ' inv' : ''}`;
    case KIND.LINEV: return `vert${e.elMean > 0 ? '↑' : '↓'} ${e.dur.toFixed(1)}s`;
    case KIND.TURN: return `turn ${deg(Math.abs(e.dAz))} @${deg(Math.abs(e.bankMean))}`;
    case KIND.SPIN: return `spin ${(Math.abs(e.dAz) / 360).toFixed(2)}t`;
    case KIND.PIVOT: return `pivot ${deg(Math.abs(e.ir))}`;
    case KIND.LEVEL: return `level ${e.dur.toFixed(1)}s`;
    default: return `? ${e.dur.toFixed(1)}s`;
  }
}
