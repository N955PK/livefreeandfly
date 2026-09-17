// Figure matching and grading for the IAC Primary figures, per the IAC Official Contest Rules 2025
// (chapters 26–28) with CIVA Appendix B where the IAC text is silent. A figure from the detector — an
// ordered list of elements — is matched to a template, measured, and graded from 10.0 down in 0.5 steps.
//
// Judging frames: horizontals and looping segments on the flight path, verticals and 45s on attitude
// (zero-lift axis = IMU axis by ruling), 1 point per 5°, HZ at 90°. Two standards are produced: the
// judge-like grade (quarter one sets the radius, only what a judge could see) and the absolute numbers.
import { KIND } from './detector.js';
import { angleDiff } from './features.js';

const RAD = Math.PI / 180;
const M_TO_FT = 3.28084;

export const PRIMARY = ['45 up line', 'spin', 'half cuban', 'loop', '180 turn', 'slow roll'];
/// The IAC Primary Known in flying order with figure K (OpenAero, IAC 2025 rules); 58 K total.
export const PRIMARY_KNOWN = [
  { type: '45 up line', k: 7 }, { type: 'spin', k: 13 }, { type: 'half cuban', k: 14 },
  { type: 'loop', k: 10 }, { type: '180 turn', k: 4 }, { type: 'slow roll', k: 10 },
];

// ---------------------------------------------------------------- helpers

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const half = (pts) => Math.round(pts * 2) / 2;          // grades move in 0.5 steps (26.1.4)
const perFive = (deg) => half(Math.abs(deg) / 5);        // 1 point per 5°, 0.5 per 2.5° (27.6)
const median = (a) => { if (!a.length) return NaN; const b = [...a].sort((x, y) => x - y); return b[(b.length - 1) >> 1]; };
const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN);

/// Drop tiny OTHER fragments and merge same-kind neighbours so templates see the intended structure.
function normalize(elements) {
  const out = [];
  for (const e of elements) {
    if (e.kind === KIND.OTHER && e.dur < 0.6) continue;
    const prev = out[out.length - 1];
    if (prev && prev.kind === e.kind && e.kind !== KIND.ROLL && Math.sign(prev.qMean) === Math.sign(e.qMean)) {
      out[out.length - 1] = mergeElements(prev, e);
    } else out.push({ ...e });
  }
  return out;
}

function mergeElements(a, b) {
  const n = (a.samples?.length || 1) + (b.samples?.length || 1);
  return {
    ...a, t1: b.t1, dur: b.t1 - a.t0, ip: a.ip + b.ip, iq: a.iq + b.iq, ir: a.ir + b.ir, iUp: (a.iUp || 0) + (b.iUp || 0), dAz: a.dAz + b.dAz,
    dAlt: a.dAlt + b.dAlt, altMin: Math.min(a.altMin, b.altMin), altMax: Math.max(a.altMax, b.altMax),
    nzMin: Math.min(a.nzMin, b.nzMin), nzMax: Math.max(a.nzMax, b.nzMax),
    elMean: (a.elMean * (a.samples?.length || 1) + b.elMean * (b.samples?.length || 1)) / n, el1: b.el1,
    gs1: b.gs1, gsMin: Math.min(a.gsMin, b.gsMin), gsMax: Math.max(a.gsMax, b.gsMax),
    inverted1: b.inverted1, trk1: b.trk1, az1: b.az1, samples: [...(a.samples || []), ...(b.samples || [])],
  };
}

/// Looping segment radii per sector of `sectorDeg` of cumulative pitch, from speed / pitch rate (metres).
function sectorRadii(loopEl, sectorDeg = 90, maxSectors = 4) {
  const out = []; let acc = 0, cur = [], sectorStart = 0;
  const s = loopEl.samples || [];
  for (let i = 1; i < s.length && out.length < maxSectors; i += 1) {
    const dt = s[i].t - s[i - 1].t;
    const q = Math.abs(s[i].q);
    if (q > 3) cur.push(s[i].tas / (q * RAD));
    acc += q * dt;
    if (acc >= sectorDeg * (out.length + 1)) { out.push(median(cur)); cur = []; sectorStart = acc; }
  }
  // A trailing partial sector only counts if it spans most of a sector's worth of arc.
  if (out.length < maxSectors && cur.length >= 5 && acc - sectorStart >= 0.45 * sectorDeg) out.push(median(cur));
  return out;
}

/// IAC 27.10.4 method 2: quarter one is the standard; each other sector visible → 1, 1:2 → 2, worse → 3.
function radiusDowngrades(radii, label) {
  const items = [];
  if (radii.length < 2 || !Number.isFinite(radii[0])) return items;
  radii.slice(1).forEach((r, i) => {
    if (!Number.isFinite(r)) return;
    const ratio = r / radii[0];
    let pts = 0;
    if (ratio <= 1 / 3 || ratio >= 3) pts = 3; else if (ratio <= 0.5 || ratio >= 2) pts = 2; else if (Math.abs(ratio - 1) > 0.2) pts = 1;
    if (pts) {
      const shape = ratio < 1 ? 'pinched' : 'opened up';
      items.push({ pts, text: `${label} sector ${i + 2} ${shape}`, detail: `radius ${Math.round(r)} m vs ${Math.round(radii[0])} m in sector 1 (${Math.round(ratio * 100)} %)`,
        fix: ratio < 1 ? 'ease the pull there — keep the radius you set in the first quarter' : 'a touch more pull there — the radius grew' , rule: '27.10.4' });
    }
  });
  return items;
}

/// Roll-rate constancy (28.20.1): split the roll into quarters of rotation; each quarter whose mean |p|
/// differs from the whole by more than 20 % is one variation, one point each.
function rollRateVariations(rollEl) {
  const s = rollEl.samples || [];
  if (s.length < 6) return { pts: 0, detail: '' };
  const total = Math.abs(rollEl.ip);
  const rates = [[], [], [], []];
  let acc = 0;
  for (let i = 1; i < s.length; i += 1) {
    acc += Math.abs(s[i].p) * (s[i].t - s[i - 1].t);
    const frac = acc / Math.max(1, total);
    if (frac < 0.1 || frac > 0.9) continue;                 // the start and stop ramps are not "rate"
    const k = Math.min(3, Math.floor(((frac - 0.1) / 0.8) * 4));
    rates[k].push(Math.abs(s[i].p));
  }
  const means = rates.map(mean).filter(Number.isFinite);
  const all = mean(means);
  const varied = means.filter((m) => Math.abs(m - all) / all > 0.3).length;
  return { pts: Math.min(3, varied), detail: `rate by quarter ${means.map((m) => Math.round(m)).join('/')} °/s` };
}

/// Length of a line element in metres (flight-path speed integrated).
function lineLength(el) {
  const s = el.samples || [];
  let d = 0;
  for (let i = 1; i < s.length; i += 1) d += s[i].tas * (s[i].t - s[i - 1].t);
  return d;
}

/// 27.9.4: two line segments that must match — visible (< 2:1) 1, 2:1–3:1 2, ≥ 3:1 3, one missing 4.
function lineLengthDowngrade(before, after, what) {
  if (before < 15 && after < 15) return { pts: 2, text: `no line before or after the ${what}`, rule: '27.9.4e' };
  if (before < 15 || after < 15) return { pts: 4, text: `no line ${before < 15 ? 'before' : 'after'} the ${what}`, rule: '27.9.4d' };
  const ratio = Math.max(before, after) / Math.min(before, after);
  const detail = `${Math.round(before)} m before, ${Math.round(after)} m after`;
  if (ratio >= 3) return { pts: 3, text: `${what} far off centre`, detail, rule: '27.9.4c' };
  if (ratio >= 2) return { pts: 2, text: `${what} off centre`, detail, rule: '27.9.4b' };
  if (ratio > 1.25) return { pts: 1, text: `${what} slightly off centre`, detail, rule: '27.9.4a' };
  return null;
}

/// Bank angle where it is meaningful (nose within 60° of the horizon): 90th percentile of |bank|.
function bankError(samples) {
  const b = samples.filter((f) => Math.abs(f.el) < 60 && Number.isFinite(f.bank)).map((f) => Math.abs(f.inverted ? angleDiff(f.bank, 180) : f.bank)).sort((x, y) => x - y);
  return b.length ? b[Math.floor(b.length * 0.9)] : 0;
}

/// Heading reference: the nearest box axis when a box exists, else the figure's own entry heading.
function axisError(az, ctx, expectedFromEntry) {
  if (Number.isFinite(ctx.axisDeg)) {
    const errs = [0, 90, 180, 270].map((k) => Math.abs(angleDiff(az, ctx.axisDeg + k)));
    return Math.min(...errs);
  }
  return Math.abs(angleDiff(az, expectedFromEntry));
}

function item(pts, text, extra = {}) { return pts > 0 ? { pts: half(pts), text, ...extra } : null; }
function meanAngle(degs) {
  let x = 0, y = 0;
  for (const d of degs) { x += Math.cos(d * RAD); y += Math.sin(d * RAD); }
  return ((Math.atan2(y, x) / RAD) + 360) % 360;
}

// ---------------------------------------------------------------- templates

const T = {
  loop(els) {
    const loop = els.find((e) => e.kind === KIND.LOOP && e.qMean > 0 && Math.abs(e.iq) > 270);
    if (!loop || els.some((e) => (e.kind === KIND.ROLL && Math.abs(e.ip) > 60) || [KIND.PIVOT, KIND.SPIN, KIND.LINEV].includes(e.kind))) return null;
    return { key: 'loop', loop, fit: 1 - Math.abs(Math.abs(loop.iq) - 360) / 180 };
  },
  'slow roll'(els) {
    const roll = els.find((e) => e.kind === KIND.ROLL && Math.abs(e.ip) > 250);
    if (!roll || els.some((e) => (e.kind === KIND.LOOP && Math.abs(e.iq) > 60) || [KIND.PIVOT, KIND.SPIN, KIND.LINEV, KIND.LINE45, KIND.TURN].includes(e.kind))) return null;
    return { key: 'slow roll', roll, fit: 1 - Math.abs(Math.abs(roll.ip) - 360) / 180 };
  },
  '180 turn'(els) {
    const turn = els.find((e) => e.kind === KIND.TURN && Math.abs(e.dAz) > 100);
    if (!turn) return null;
    const i = els.indexOf(turn);
    const rollIn = els[i - 1]?.kind === KIND.ROLL ? els[i - 1] : null, rollOut = els[i + 1]?.kind === KIND.ROLL ? els[i + 1] : null;
    return { key: '180 turn', turn, rollIn, rollOut, fit: 1 - Math.abs(Math.abs(turn.dAz) - 180) / 180 };
  },
  '45 up line'(els) {
    const line = els.find((e) => e.kind === KIND.LINE45 && e.elMean > 0 && e.dur > 0.8);
    const foreign = els.some((e) => [KIND.PIVOT, KIND.SPIN, KIND.LINEV, KIND.TURN].includes(e.kind)
      || (e.kind === KIND.ROLL && Math.abs(e.ip) > 60) || (e.kind === KIND.LOOP && Math.abs(e.iq) > 120));
    if (!line || foreign) return null;
    return { key: '45 up line', line, fit: 0.9 };
  },
  'half cuban'(els) {
    const loop = els.find((e) => e.kind === KIND.LOOP && e.qMean > 0 && Math.abs(e.iq) > 160 && Math.abs(e.iq) < 290);
    if (!loop) return null;
    const i = els.indexOf(loop);
    const after = els.slice(i + 1);
    const roll = after.find((e) => e.kind === KIND.ROLL && Math.abs(e.ip) > 100);
    if (!roll) return null;
    const j = after.indexOf(roll);
    const lineBefore = after.slice(0, j).find((e) => e.kind === KIND.LINE45 && e.elMean < 0) || null;
    const lineAfter = after.slice(j + 1).find((e) => e.kind === KIND.LINE45 && e.elMean < 0) || null;
    const exitPull = after.slice(j + 1).find((e) => e.kind === KIND.LOOP && e.qMean > 0) || null;
    return { key: 'half cuban', loop, roll, lineBefore, lineAfter, exitPull, fit: 1 - Math.abs(Math.abs(loop.iq) - 225) / 180 };
  },
  spin(els) {
    const spin = els.find((e) => e.kind === KIND.SPIN && Math.abs(e.iUp) > 200);
    if (!spin) return null;
    const i = els.indexOf(spin);
    const down = els.slice(i + 1).find((e) => e.kind === KIND.LINEV && e.elMean < 0) || null;
    const pull = els.slice(i + 1).find((e) => e.kind === KIND.LOOP && e.qMean > 0) || null;
    return { key: 'spin', spin, down, pull, fit: 0.9 };
  },
};

/// Best-matching Primary template for a detected figure, or null. `want` restricts to one type.
export function matchFigure(fig, want) {
  const els = normalize(fig.elements);
  let best = null;
  for (const key of want ? [want] : PRIMARY) {
    const m = T[key](els);
    if (m && (!best || m.fit > best.fit)) best = { ...m, els };
  }
  return best;
}

// ---------------------------------------------------------------- grading

export function gradeFigure(fig, ctx = {}, want) {
  const m = matchFigure(fig, want);
  if (!m) return null;
  const items = [];
  const entry = fig.entry;
  // Entry heading from the settled part of the line before the figure (the last frames may already be moving).
  const entryAz = entry?.samples?.length > 12 ? meanAngle(entry.samples.slice(-40, -10).map((f) => f.az)) : (entry ? entry.az1 : m.els[0].az0);
  // Direction of travel into the figure (ground track of the settled entry line), for figures graded by where
  // the aircraft flew rather than where its nose pointed.
  const entryTrk = entry?.samples?.length > 12 ? meanAngle(entry.samples.slice(-40, -10).map((f) => f.trk)) : NaN;
  if (entry && entry.dur < 1.0) items.push(item(1, 'no distinct line before the figure', { detail: `${entry.dur.toFixed(1)} s level`, rule: '26.7.1', fix: 'show a horizontal line — a good second — before starting' }));
  let hz = null;

  // Entry line: wings level, horizontal, on axis (26.1.8, 27.6). Exit is checked per figure below.
  if (Number.isFinite(ctx.axisDeg) && Math.min(...[0, 90, 180, 270].map((k) => Math.abs(angleDiff(entryAz, ctx.axisDeg + k)))) > 30) {
    ctx = { ...ctx, axisDeg: NaN };   // not flying this box's axes — grade against the figure's own entry heading
  }
  if (entry && entry.samples?.length > 12) {
    const tail = entry.samples.slice(-40, -10);
    const b = median(tail.filter((f) => Number.isFinite(f.bank)).map((f) => Math.abs(f.inverted ? angleDiff(f.bank, 180) : f.bank))); if (b > 4) items.push(item(perFive(b), 'entry not wings level', { detail: `${Math.round(b)}° bank`, rule: '27.6' }));
    const fpa = Math.abs(mean(tail.map((f) => f.fpa))); if (fpa > 4) items.push(item(perFive(fpa), `entry ${mean(tail.map((f) => f.fpa)) > 0 ? 'climbing' : 'descending'}`, { detail: `${Math.round(fpa)}° flight path`, rule: '27.5' }));
    const axErr = axisError(entryAz, ctx, entryAz); if (axErr > 4) items.push(item(perFive(axErr), 'entry off the box axis', { detail: `${Math.round(axErr)}°`, rule: '26.1.8' }));
  }

  const exitAz = Number.isFinite(fig.exitAz) ? fig.exitAz : m.els[m.els.length - 1].az1;
  const exitCheck = (expected) => {
    const err = axisError(exitAz, ctx, expected);
    if (err >= 90) hz = 'exit direction 90° or more off';
    else if (err > 4) items.push(item(perFive(err), `exit heading ${Math.round(err)}° off`, { detail: `exit ${Math.round(exitAz)}°`, rule: '27.6', fix: 'hold the axis with rudder through the exit' }));
  };

  switch (m.key) {
    case 'loop': {
      const radii = sectorRadii(m.loop, 90);
      items.push(...radiusDowngrades(radii, 'loop'));
      const b = bankError(m.loop.samples); if (b > 4) items.push(item(perFive(b), 'wing low in the loop', { detail: `${Math.round(b)}° bank`, rule: '28.11 / 27.6', fix: 'keep the wings level — check the horizon at the top' }));
      const dAlt = m.loop.samples.length ? (m.loop.samples[m.loop.samples.length - 1].alt - m.loop.samples[0].alt) : 0;
      if (Math.abs(dAlt) > 40) items.push(item(Math.min(3, Math.abs(dAlt) / 100), `exit ${Math.round(Math.abs(dAlt))} ft ${dAlt > 0 ? 'above' : 'below'} the entry`, { rule: '27.10.3', fix: dAlt < 0 ? 'the back half is too tight or too fast — float the last quarter' : 'the last quarter was too shallow' }));
      const extent = Math.abs(m.loop.iq); if (extent < 300) hz = 'loop not completed';
      exitCheck(entryAz);
      return finish('loop', m, items, hz, { radii: radii.map((r) => Math.round(r)), extentDeg: Math.round(extent), dAltFt: Math.round(dAlt) }, fig, ctx);
    }
    case 'slow roll': {
      const extent = Math.abs(m.roll.ip);
      const err = extent - 360;
      if (Math.abs(err) >= 90) hz = 'roll 90° or more off';
      else if (Math.abs(err) > 4) items.push(item(perFive(err), `${err > 0 ? 'over' : 'under'}-rotated ${Math.round(Math.abs(err))}°`, { rule: '28.20.2', fix: 'stop the roll crisply on the wings-level picture' }));
      const rv = rollRateVariations(m.roll); if (rv.pts) items.push(item(rv.pts, `${rv.pts} roll-rate variation${rv.pts > 1 ? 's' : ''}`, { detail: rv.detail, rule: '28.20.1', fix: 'constant aileron through the roll — most pilots slow through inverted' }));
      const fpa = mean(m.roll.samples.map((f) => f.fpa)); if (Math.abs(fpa) > 4) items.push(item(perFive(fpa), `flight path ${fpa > 0 ? 'climbed' : 'sank'} through the roll`, { detail: `${Math.round(fpa)}° average flight path`, rule: '28.20.3', fix: fpa < 0 ? 'more forward stick while inverted' : 'less back pressure on the way in' }));
      const dAz = Math.abs(m.roll.dAz); if (dAz > 4) items.push(item(perFive(dAz), `heading changed ${Math.round(dAz)}° during the roll`, { rule: '28.20.3', fix: 'rudder against the heading swing in the knife-edge parts' }));
      exitCheck(entryAz);
      return finish('slow roll', m, items, hz, { extentDeg: Math.round(extent), fpaDeg: Math.round(fpa) }, fig, ctx);
    }
    case '180 turn': {
      const ts = m.turn.samples, core = ts.slice(Math.floor(ts.length * 0.15), Math.ceil(ts.length * 0.85));
      const banks = core.map((f) => Math.abs(f.bank)).filter(Number.isFinite).sort((x, y) => x - y);
      const bank = banks.length ? banks[banks.length >> 1] : Math.abs(m.turn.bankMean);
      if (bank < 60) items.push(item(perFive(60 - bank), `bank only ${Math.round(bank)}°`, { rule: '28.5.2', fix: 'roll to at least 60° before the turn starts' }));
      const lo = banks[Math.floor(banks.length * 0.1)] ?? bank, hi = banks[Math.floor(banks.length * 0.9)] ?? bank;
      if (hi - lo > 8) items.push(item(perFive(hi - lo - 3), 'bank changed during the turn', { detail: `${Math.round(lo)}–${Math.round(hi)}°`, rule: '28.5.3', fix: 'set the bank once and hold it with aileron' }));
      const dAlt = m.turn.dAlt; if (Math.abs(dAlt) > 40) items.push(item(Math.abs(dAlt) / 100, `${dAlt > 0 ? 'climbed' : 'descended'} ${Math.round(Math.abs(dAlt))} ft in the turn`, { rule: '28.4.5', fix: dAlt > 0 ? 'less back pressure — hold the horizon on the cowl' : 'more back pressure in the turn' }));
      const turned = Math.abs(angleDiff(exitAz, entryAz)) || Math.abs(m.turn.dAz);
      const turnErr = turned - 180; if (Math.abs(turnErr) > 4 && Math.abs(turnErr) < 90) items.push(item(perFive(turnErr), `turned ${Math.round(turned)}°`, { rule: '28.4.6' }));
      if (m.rollIn && m.rollOut) {
        const rin = Math.abs(m.rollIn.pMean), rout = Math.abs(m.rollOut.pMean);
        if (Math.abs(rin - rout) / Math.max(rin, rout) > 0.25) items.push(item(1, 'roll-in and roll-out rates differ', { detail: `${Math.round(rin)} vs ${Math.round(rout)} °/s`, rule: '28.5.4' }));
      }
      exitCheck(entryAz + 180);
      return finish('180 turn', m, items, hz, { bankDeg: Math.round(bank), turnDeg: Math.round(turned), dAltFt: Math.round(dAlt) }, fig, ctx);
    }
    case '45 up line': {
      const el = m.line.elMean, err = el - 45;
      if (Math.abs(err) > 3) items.push(item(perFive(err), `line ${err > 0 ? 'steep' : 'shallow'} at ${Math.round(el)}°`, { rule: '27.4', fix: err < 0 ? 'set the 45 with the wingtip sight, it looks steeper than it is from the seat' : 'a little less pitch — you are past 45' }));
      if (m.line.elStd > 3) items.push(item(1, 'attitude wandered on the line', { detail: `±${Math.round(m.line.elStd)}°`, rule: 'B.8.1.3' }));
      const b = bankError(m.line.samples); if (b > 4) items.push(item(perFive(b), 'wing low on the line', { detail: `${Math.round(b)}°`, rule: '27.6' }));
      const drift = Math.abs(m.line.dAz); if (drift > 4) items.push(item(perFive(drift), `heading drifted ${Math.round(drift)}° on the line`, { rule: '27.6', fix: 'rudder to hold heading as the speed decays' }));
      exitCheck(entryAz);
      return finish('45 up line', m, items, hz, { lineDeg: Math.round(el), lineSeconds: Math.round(m.line.dur * 10) / 10 }, fig, ctx);
    }
    case 'half cuban': {
      const radii = sectorRadii(m.loop, 90, 3);
      items.push(...radiusDowngrades(radii, '⅝ loop'));
      const b = bankError(m.loop.samples); if (b > 4) items.push(item(perFive(b), 'wing low in the loop', { detail: `${Math.round(b)}°`, rule: '27.6' }));
      const lines = [m.lineBefore, m.lineAfter].filter(Boolean);
      for (const ln of lines) {
        const err = Math.abs(ln.elMean) - 45;
        if (Math.abs(err) > 3) items.push(item(perFive(err), `45° down line ${err > 0 ? 'steep' : 'shallow'} at ${Math.round(Math.abs(ln.elMean))}°${ln.inverted0 ? ' (inverted)' : ''}`, { rule: '27.4', fix: 'hold the 45 — look at the wingtip against the horizon' }));
      }
      const rollErr = Math.abs(m.roll.ip) - 180;
      if (Math.abs(rollErr) >= 90) hz = 'half roll 90° or more off';
      else if (Math.abs(rollErr) > 4) items.push(item(perFive(rollErr), `half roll ${rollErr > 0 ? 'over' : 'under'}-rotated ${Math.round(Math.abs(rollErr))}°`, { rule: '28.20.2' }));
      const before = m.lineBefore ? lineLength(m.lineBefore) : 0, after = m.lineAfter ? lineLength(m.lineAfter) : 0;
      const ll = lineLengthDowngrade(before, after, 'half roll'); if (ll) items.push(ll);
      exitCheck(entryAz + 180);
      return finish('half cuban', m, items, hz, { radii: radii.map((r) => Math.round(r)), lineBeforeM: Math.round(before), lineAfterM: Math.round(after), rollDeg: Math.round(Math.abs(m.roll.ip)) }, fig, ctx);
    }
    case 'spin': {
      // Turns: whole turns from the integrated rotation about the vertical over the whole figure (the break
      // starts rotating before the per-sample rule calls it a spin), the fraction from the heading where the
      // rotation stopped relative to the entry heading. The gyros read ~10 % low, so the integral only picks n.
      const lastIdx = m.els.indexOf(m.down || m.spin);
      const iUpTotal = m.els.slice(0, lastIdx + 1).reduce((a, e) => a + (e.iUp || 0), 0);
      const dir = Math.sign(iUpTotal || 1);
      // Direction of travel, not nose heading, defines the spin's entry and exit direction: the nose azimuth is
      // meaningless near the vertical, and a crabbed entry/exit line points the nose off the line it flies. The
      // turn count stays the aircraft's own heading rotation (iUpTotal); the residual is how far the exit direction
      // of travel came round from the entry direction (28.24.6 — a 1.5-turn spin flies out 180° reversed).
      const dirIn = Number.isFinite(entryTrk) ? entryTrk : entryAz;
      const dirOut = Number.isFinite(fig.exitTrk) ? fig.exitTrk : exitAz;
      const residual = ((dir * angleDiff(dirOut, dirIn)) + 360) % 360;   // 0..360 in the spin's direction
      const target = Math.abs(iUpTotal) / 0.9;
      let rotation = residual;
      for (let k = 1; k <= 3; k += 1) { const c = k * 360 + residual; if (Math.abs(c - target) < Math.abs(rotation - target)) rotation = c; }
      const turns = rotation / 360;
      const want = ctx.spinTurns ?? 1.5;
      const rotErr = (turns - want) * 360;
      if (Math.abs(rotErr) >= 90) hz = `spin stopped ${Math.round(Math.abs(rotErr))}° from the heading`;
      else if (Math.abs(rotErr) > 4) items.push(item(perFive(rotErr), `stopped ${Math.round(Math.abs(rotErr))}° ${rotErr > 0 ? 'past' : 'short of'} the heading`, { rule: '28.24.6', fix: 'lead the recovery — opposite rudder about a quarter turn early' }));
      // Entry: the CG must not rise into the break and pitch, yaw and roll must start together (28.24.2).
      if (entry?.samples?.length > 25) {
        const s = entry.samples, last = s[s.length - 1], earlier = s[Math.max(0, s.length - 25)];
        if (last.alt - earlier.alt > 25) items.push(item(1, 'nose pulled up into the break', { detail: `+${Math.round(last.alt - earlier.alt)} ft in the last second`, rule: '28.24.2 / B.9.29.3', fix: 'let it stall level — hold altitude with elevator, not more' }));
      }
      if (m.down) { const err = Math.abs(m.down.elMean) - 90; if (Math.abs(err) > 4) items.push(item(perFive(err), `down line ${Math.round(Math.abs(m.down.elMean))}°`, { rule: '27.3', fix: 'push to a true vertical after the rotation stops' })); }
      else items.push(item(1, 'no vertical down line shown', { rule: '28.24.8' }));
      // The stop-heading error above is the exit-heading error (charged once, 26.6.2).
      return finish('spin', m, items, hz, { turns: Math.round(turns * 100) / 100, iUpDeg: Math.round(iUpTotal), entryTrk: Math.round(dirIn), exitTrk: Math.round(dirOut), residual: Math.round(residual), want, downDeg: m.down ? Math.round(Math.abs(m.down.elMean)) : null }, fig, ctx);
    }
    default: return null;
  }
}

function finish(type, m, rawItems, hz, measurements, fig, ctx) {
  const items = rawItems.filter(Boolean).sort((a, b) => b.pts - a.pts);
  const total = items.reduce((a, b) => a + b.pts, 0);
  const score = hz ? 0 : (total >= 9.75 ? 0 : half(10 - total));
  return { type, fit: m.fit, hz, score, items, total: half(total), measurements, t0: fig.t0, t1: fig.t1, dur: fig.dur, match: m, ctx };
}

/// One-line spoken/displayed critique. `voice`: 'aircraft' (what happened + points), 'control' (adds the
/// correction), 'score' (score and the biggest item only). `max` items.
export function critique(g, voice = 'aircraft', max = 3) {
  if (!g) return '';
  const name = g.type.replace(/^\w/, (c) => c.toUpperCase());
  if (g.hz) return `${name}: hard zero — ${g.hz}.`;
  const parts = g.items.slice(0, voice === 'score' ? 1 : max).map((it) => {
    const pts = `${it.pts % 1 ? it.pts.toFixed(1) : it.pts} ${it.pts === 1 ? 'point' : 'points'}`;
    return voice === 'control' && it.fix ? `${it.text}, ${pts} — ${it.fix}` : `${it.text}, ${pts}`;
  });
  const scoreText = `score ${g.score.toFixed(1)}`;
  return parts.length ? `${name}: ${parts.join('. ')}. ${scoreText}.` : `${name}: clean. ${scoreText}.`;
}
