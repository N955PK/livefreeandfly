// Aresti-style figure drawing (clean-room, stylized). Turns parsed OLAN figures (olan.js) + their resolved catalogue
// entry (aresti.js) into an SVG sequence card, following the Aresti conventions: solid stroke = upright / positive-g,
// dashed = inverted / negative-g, a filled dot at the start and a short perpendicular bar at the end, a chevron with a
// count for rolls, and a small triangle for spins/snaps. Geometry is a recognizable schematic, not competition-exact;
// a figure with no geometry yet renders as a labelled placeholder so any imported sequence still shows something.
import { parseSequence, figures as figureItems } from './olan.js';
import { resolve, sequenceK } from './aresti.js';

const RAD = Math.PI / 180;
const L = 26, R = 13, S = 7;   // line length, loop radius, short entry/exit stub — in local drawing units

// --- turtle: walks the flight path, splitting the stroke whenever attitude (solid/dashed) flips ---
function newTurtle() { return { x: 0, y: 0, h: 0, inv: false, strokes: [{ dash: false, pts: [[0, 0]] }], marks: [] }; }
function tip(t) { return t.strokes[t.strokes.length - 1]; }
function setInv(t, v) { if (v !== t.inv) { t.inv = v; t.strokes.push({ dash: v, pts: [[t.x, t.y]] }); } }
function fwd(t, len) { t.x += Math.cos(t.h * RAD) * len; t.y -= Math.sin(t.h * RAD) * len; tip(t).pts.push([t.x, t.y]); }
function arc(t, sweep, r) {   // sweep>0 curves the heading up-and-over (CCW in screen), r = radius
  const steps = Math.max(6, Math.round(Math.abs(sweep) / 12));
  const seg = sweep / steps;
  const chord = 2 * r * Math.sin(Math.abs(seg) * RAD / 2);
  for (let i = 0; i < steps; i += 1) { t.h += seg; fwd(t, chord); }
}
function mark(t, kind, label) { t.marks.push({ x: t.x, y: t.y, h: t.h, kind, label }); }

// Roll code -> compact label (turns). Spin/snap codes carry s/f.
const ROLL_LABEL = { 0: '', 1: '1', 2: '½', 3: '¾', 4: '¼', 5: '1¼', 6: '1½', 7: '1¾', 8: '2', 9: '2' };
function rollLabel(code) {
  const digits = code.replace(/[^0-9]/g, '');
  return ROLL_LABEL[digits] ?? digits;
}
// Place the figure's rolls (or a spin/snap) along a segment of length `len`, centered.
function rollsAlong(t, fig, len) {
  const half = len / 2;
  fwd(t, half);
  for (const r of fig.rolls) {
    if (/s/.test(r.code)) mark(t, 'spin', rollLabel(r.code));
    else if (/f/.test(r.code)) mark(t, 'snap', rollLabel(r.code));
    else mark(t, 'roll', rollLabel(r.code));
  }
  fwd(t, half);
}

// Geometry per base figure. Each draws a schematic path and drops roll/spin markers where they belong.
const GEO = {
  line0: (t, f) => { rollsAlong(t, f, L * 1.4); },                                   // horizontal line (rolling line)
  d: (t, f) => { fwd(t, S); arc(t, 45, R); rollsAlong(t, f, L); arc(t, -45, R); fwd(t, S); },
  id: (t, f) => { fwd(t, S); arc(t, -45, R); rollsAlong(t, f, L); arc(t, 45, R); fwd(t, S); },
  v: (t, f) => { fwd(t, S); arc(t, 90, R); rollsAlong(t, f, L); arc(t, -90, R); fwd(t, S); },
  iv: (t, f) => { fwd(t, S); arc(t, -90, R); rollsAlong(t, f, L); arc(t, 90, R); fwd(t, S); },
  o: (t, f) => { fwd(t, S); if (f.rolls.length) { arc(t, 180, R * 1.5); rollsAlong(t, f, 2); arc(t, 180, R * 1.5); } else arc(t, 360, R * 1.5); fwd(t, S); },
  a: (t) => { fwd(t, S); setInv(t, true); arc(t, -180, R * 1.4); setInv(t, false); fwd(t, S); },   // split-S
  m: (t) => { fwd(t, S); arc(t, 180, R * 1.4); setInv(t, true); fwd(t, S); },                       // Immelmann
  c: (t, f) => { fwd(t, S); arc(t, 225, R * 1.3); rollsAlong(t, f, L); arc(t, 45, R); fwd(t, S); }, // half Cuban
  h: (t, f) => { fwd(t, S); arc(t, 90, R); fwd(t, L); mark(t, 'pivot', ''); t.h = -90; fwd(t, L); arc(t, 90, R); fwd(t, S); rollsAlong(t, { rolls: [] }, 0.1); void f; }, // hammerhead
  spin: (t, f) => { fwd(t, S); mark(t, 'spin', spinLabel(f)); t.h = -90; fwd(t, L * 1.2); arc(t, 90, R); fwd(t, S); },
  turn: (t, f) => { fwd(t, S); mark(t, 'turn', turnLabel(f)); fwd(t, L * 1.4); },
};
function spinLabel(fig) { const r = fig.rolls.find((x) => /s/.test(x.code)); return r ? `${rollLabel(r.code)} spin` : 'spin'; }
function turnLabel(fig) { const deg = { '': 90, 2: 180, 3: 270, 4: 360 }; const p = fig.prefix.replace(/[^0-9]/g, ''); return `${deg[p] ?? 180}°`; }

// Pick the geometry for a parsed figure.
function geoFor(fig) {
  if (fig.base === 'j') return GEO.turn;
  if (fig.rolls.some((r) => /s/.test(r.code))) return GEO.spin;   // any spin -> spin glyph + down line
  if (fig.base === '' ) return GEO.line0;                          // rolling horizontal line (slow roll etc.)
  return GEO[fig.base] || null;
}

function bbox(t) {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const s of t.strokes) for (const [x, y] of s.pts) { minx = Math.min(minx, x); miny = Math.min(miny, y); maxx = Math.max(maxx, x); maxy = Math.max(maxy, y); }
  for (const m of t.marks) { minx = Math.min(minx, m.x); miny = Math.min(miny, m.y); maxx = Math.max(maxx, m.x); maxy = Math.max(maxy, m.y); }
  if (!Number.isFinite(minx)) { minx = miny = 0; maxx = maxy = 1; }
  return { minx, miny, maxx, maxy };
}

function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

// Draw one figure into a WxH cell; returns an SVG group string. Scales the schematic to fit with margin.
function figureCellSVG(item, res, index, W, drawH) {
  const t = newTurtle();
  const g = geoFor(item);
  let placeholder = false;
  if (g) g(t, item); else { fwd(t, L); placeholder = true; }
  const b = bbox(t);
  const pad = 16, span = Math.max(b.maxx - b.minx, b.maxy - b.miny, 1);
  const scale = Math.min((W - pad * 2) / span, (drawH - pad * 2) / span);
  const ox = (W - (b.maxx - b.minx) * scale) / 2 - b.minx * scale;
  const oy = (drawH - (b.maxy - b.miny) * scale) / 2 - b.miny * scale;
  const px = (x) => (x * scale + ox).toFixed(1);
  const py = (y) => (y * scale + oy).toFixed(1);
  let s = `<g>`;
  for (const st of t.strokes) {
    if (st.pts.length < 2) continue;
    const d = st.pts.map((p, i) => `${i ? 'L' : 'M'}${px(p[0])} ${py(p[1])}`).join(' ');
    s += `<path d="${d}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${st.dash ? ' stroke-dasharray="4 4"' : ''}/>`;
  }
  // start dot + end bar
  const first = t.strokes[0].pts[0]; const lastStroke = t.strokes[t.strokes.length - 1]; const last = lastStroke.pts[lastStroke.pts.length - 1];
  s += `<circle cx="${px(first[0])}" cy="${py(first[1])}" r="3.5" fill="currentColor"/>`;
  const eh = t.h * RAD; const bx = Math.cos(eh + Math.PI / 2), by = -Math.sin(eh + Math.PI / 2);
  s += `<line x1="${(last[0] * scale + ox - bx * 6).toFixed(1)}" y1="${(last[1] * scale + oy - by * 6).toFixed(1)}" x2="${(last[0] * scale + ox + bx * 6).toFixed(1)}" y2="${(last[1] * scale + oy + by * 6).toFixed(1)}" stroke="currentColor" stroke-width="2"/>`;
  for (const m of t.marks) {
    const x = m.x * scale + ox, y = m.y * scale + oy;
    if (m.kind === 'spin' || m.kind === 'snap') s += `<path d="M${(x - 5).toFixed(1)} ${(y - 5).toFixed(1)} L${(x + 5).toFixed(1)} ${(y - 5).toFixed(1)} L${x.toFixed(1)} ${(y + 6).toFixed(1)} Z" fill="currentColor"/>`;
    else if (m.kind === 'roll') s += `<path d="M${(x - 5).toFixed(1)} ${(y - 5).toFixed(1)} L${x.toFixed(1)} ${y.toFixed(1)} L${(x - 5).toFixed(1)} ${(y + 5).toFixed(1)}" fill="none" stroke="currentColor" stroke-width="2"/>`;
    else if (m.kind === 'pivot') s += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" fill="currentColor"/>`;
    if (m.label) s += `<text x="${(x + 7).toFixed(1)}" y="${(y - 6).toFixed(1)}" font-size="9" fill="currentColor" opacity="0.85">${esc(m.label)}</text>`;
  }
  // number badge + name + K below the drawing
  const kTxt = res.k != null ? `K${res.k}` : (placeholder || !res.exact ? 'K?' : '');
  const nm = res.name.length > 24 ? `${res.name.slice(0, 23)}…` : res.name;
  s += `<text x="6" y="16" font-size="12" font-weight="700" fill="currentColor">${index + 1}</text>`;
  s += `<text x="${W / 2}" y="${drawH + 14}" font-size="9" text-anchor="middle" fill="currentColor" opacity="0.9">${esc(nm)}</text>`;
  s += `<text x="${W / 2}" y="${drawH + 26}" font-size="9" text-anchor="middle" fill="currentColor" opacity="0.7">${esc(item.raw)}${kTxt ? ` · ${kTxt}` : ''}</text>`;
  s += `</g>`;
  return s;
}

/// Render a whole sequence (OLAN string) as an SVG card. Returns an SVG string; `color` themes the strokes/text.
export function sequenceSVG(olanString, { perRow = 4, cellW = 150, drawH = 130, color = 'currentColor' } = {}) {
  const items = figureItems(parseSequence(olanString));
  const resolved = items.map(resolve);
  const cellH = drawH + 34;
  const rows = Math.ceil(items.length / perRow) || 1;
  const width = perRow * cellW;
  const height = rows * cellH + 8;
  let body = '';
  items.forEach((item, i) => {
    const cx = (i % perRow) * cellW, cy = Math.floor(i / perRow) * cellH;
    body += `<g transform="translate(${cx},${cy})">${figureCellSVG(item, resolved[i], i, cellW, drawH)}</g>`;
  });
  const total = sequenceK(resolved);
  const kline = `Total K ${total.k}${total.complete ? '' : '+'}`;
  return `<svg viewBox="0 0 ${width} ${height + 18}" xmlns="http://www.w3.org/2000/svg" style="color:${color};font-family:system-ui,sans-serif">`
    + body
    + `<text x="${width - 6}" y="${height + 12}" font-size="11" text-anchor="end" fill="currentColor" opacity="0.85">${kline}</text>`
    + `</svg>`;
}
