// Drives the vendored OpenAero (GPL-3) as a hidden Aresti-drawing engine. renderSequence(olan) loads the OLAN string
// into a hidden, offscreen OpenAero iframe, triggers its redraw, and returns { svg, figures, valid }: a standalone SVG
// string of the drawn sequence, the parsed figures (name / Aresti number / K, straight from OpenAero), and whether the
// sequence parsed cleanly. The iframe is created lazily on first use; renders are queued because OpenAero has one
// global drawing state. Offscreen (not display:none) so getBBox has real layout.
const OA_URL = 'vendor/openaero/index.html';
let frame = null;
let readyP = null;
let queue = Promise.resolve();

function ensureFrame() {
  if (readyP) return readyP;
  frame = document.createElement('iframe');
  frame.title = 'aresti-render';
  frame.setAttribute('aria-hidden', 'true');
  frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:1200px;height:900px;border:0;visibility:hidden';
  frame.src = OA_URL;
  document.body.appendChild(frame);
  readyP = new Promise((resolve, reject) => {
    const t0 = Date.now();
    const poll = () => {
      let w = null;
      try { w = frame.contentWindow; } catch (e) { w = null; }
      if (w && w.OA && w.OA.SVGRoot && typeof w.checkSequenceChanged === 'function'
          && typeof w.launchURL === 'function' && w.OA.sequenceText) {
        // Warm one draw so the first real render isn't a cold-start race (library/draw path not yet primed).
        try { w.OA.sequenceText.innerText = 'o'; w.checkSequenceChanged(true); } catch (e) { /* ignore */ }
        return setTimeout(() => resolve(w), 300);
      }
      if (Date.now() - t0 > 20000) return reject(new Error('OpenAero did not initialise'));
      return setTimeout(poll, 150);
    };
    frame.addEventListener('load', () => setTimeout(poll, 100));
    poll();
  });
  return readyP;
}

// OpenAero fills OA.activeSequence.figures after a parse; pull the human-facing bits defensively (its internal shape
// varies by version). aresti may be an array of catalogue numbers; k an array or number.
function figureData(w) {
  const figs = (w.OA.activeSequence && w.OA.activeSequence.figures) || [];
  const out = [];
  for (const f of figs) {
    if (!f || (f.aresti == null && f.k == null)) continue;   // skip separators / moves / comments (they carry no Aresti/K)
    const aresti = Array.isArray(f.aresti) ? f.aresti.filter(Boolean).join(' + ') : (f.aresti || null);
    const k = Array.isArray(f.k) ? f.k.reduce((a, n) => a + (Number(n) || 0), 0) : (Number(f.k) || null);
    const name = Array.isArray(f.description) ? f.description.filter(Boolean).join(', ') : (f.description || '');
    out.push({ olan: f.string || f.seqString || '', aresti, k, name, family: f.superFamily || f.family || null });
  }
  return out;
}

function extractSVG(w) {
  const root = w.OA.SVGRoot;
  const seq = root && root.querySelector('#sequence');
  if (!seq) return { svg: '', figures: [], valid: false };
  const b = seq.getBBox();
  const pad = 6;   // tight margin around the drawing so it fills its container with little whitespace
  const ns = 'http://www.w3.org/2000/svg';
  const defs = root.querySelector('defs');
  const w2 = (b.width + pad * 2).toFixed(1);
  const h2 = (b.height + pad * 2).toFixed(1);
  const svg = `<svg xmlns="${ns}" viewBox="${(b.x - pad).toFixed(1)} ${(b.y - pad).toFixed(1)} ${w2} ${h2}" `
    + `preserveAspectRatio="xMidYMid meet">${defs ? defs.outerHTML : ''}${seq.outerHTML}</svg>`;
  const figures = figureData(w);
  return { svg, figures, valid: figures.length > 0, k: figures.reduce((a, f) => a + (f.k || 0), 0) };
}

/// Render an OLAN sequence string to a standalone Aresti SVG (+ parsed figure data). Queued; resolves to
/// { svg, figures, valid, k }.
export function renderSequence(olan) {
  queue = queue.then(async () => {
    const w = await ensureFrame();
    w.OA.sequenceText.innerText = olan || '';
    try { w.checkSequenceChanged(true); } catch (e) { /* OpenAero surfaces parse errors in its own UI; we read what drew */ }
    await new Promise((r) => setTimeout(r, 250));
    return extractSVG(w);
  }).catch((e) => ({ svg: '', figures: [], valid: false, error: String(e.message || e) }));
  return queue;
}

/// Render a sequence from the vendored OpenAero library by its key (e.g. '2026 IAC Primary Known'). Resolves to
/// { svg, figures, valid, k, olan } — olan is the sequence text OpenAero loaded, kept so the app can grade/store it.
export function renderLibrary(key) {
  queue = queue.then(async () => {
    const w = await ensureFrame();
    try { w.eval(`launchURL({url: library[${JSON.stringify(key)}]})`); } catch (e) { return { svg: '', figures: [], valid: false, error: `library load failed: ${e.message}` }; }
    // Poll until the load actually renders — on first use the rules worker may still be spinning up, and a Known
    // always has several figures, so wait past the warm-up single figure (up to ~3 s).
    const t0 = Date.now();
    for (;;) {
      await new Promise((r) => setTimeout(r, 150));
      const figs = ((w.OA.activeSequence && w.OA.activeSequence.figures) || []).filter((f) => f && f.aresti).length;
      if (figs > 1 || Date.now() - t0 > 3000) break;
    }
    const r = extractSVG(w);
    r.olan = (w.OA.sequenceText.innerText || '').replace(/ /g, ' ').trim();
    return r;
  }).catch((e) => ({ svg: '', figures: [], valid: false, error: String(e.message || e) }));
  return queue;
}

const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

/// Draw a list of OLAN figure tokens as a non-overlapping grid — each figure rendered on its own (so nothing can
/// collide) and tiled with a number + token + K label. Used for "what you flew", where the figures carry no layout.
/// Resolves to { svg, k, figures, valid }.
export async function renderFigureGrid(tokens, { perRow = 3, cw = 190, ch = 158, pad = 8 } = {}) {
  const list = (tokens || []).filter(Boolean);
  const cells = [];
  for (const t of list) { const r = await renderSequence(t); cells.push({ t, svg: r.svg, k: r.figures[0] ? r.figures[0].k : null }); }
  if (!cells.length) return { svg: '', k: 0, figures: [], valid: false };
  const rows = Math.ceil(cells.length / perRow) || 1;
  let body = '';
  cells.forEach((c, i) => {
    const x = (i % perRow) * cw, y = Math.floor(i / perRow) * ch;
    const vb = (c.svg.match(/viewBox="([^"]+)"/) || [])[1] || '0 0 100 100';
    const inner = c.svg.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
    body += `<svg x="${x + pad}" y="${y + pad}" width="${cw - 2 * pad}" height="${ch - 32}" viewBox="${vb}" preserveAspectRatio="xMidYMid meet">${inner}</svg>`;
    body += `<text x="${x + cw / 2}" y="${y + ch - 11}" text-anchor="middle" font-size="12" fill="currentColor" font-family="system-ui,sans-serif">${i + 1}. ${esc(c.t)}${c.k ? ` · K${c.k}` : ''}</text>`;
  });
  const W = perRow * cw, H = rows * ch;
  const k = cells.reduce((a, c) => a + (c.k || 0), 0);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" style="color:#12213f;font-family:system-ui,sans-serif">${body}</svg>`;
  return { svg, k, figures: cells.map((c) => ({ olan: c.t, k: c.k })), valid: true };
}

/// Warm up the engine ahead of first use (e.g. when the Sequences view opens).
export function preload() { ensureFrame().catch(() => {}); }
