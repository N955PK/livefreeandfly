// Clean-room parser/serializer for the OpenAero "OLAN" sequence notation — the ASCII interchange that both encodes
// an aerobatic sequence and drives its Aresti drawing. Reimplemented from the published grammar (not from OpenAero's
// GPL source). This layer only *structures* a sequence into figures and their roll/attitude parts; resolving a figure
// to its Aresti number, K-factor and drawing lives in aresti.js. Round-trip is exact: sequenceToString(parseSequence(s))
// reproduces s (modulo whitespace), because each figure keeps its raw text.
//
// A figure token is [entry][prefix-rolls][base][suffix], where the base is one of the figure letters below and rolls
// are digits/s(pin)/f(lick) attached before, after, or in (parentheses) at mid-figure positions.

// Base figures, longest first so greedy matching picks `iv` over `v`, `dhd` over `dh`/`d`, `ita` over `ta`, etc.
export const BASE_FIGURES = [
  'dhd', 'rdb', 'ipn', 'igg', 'ita',
  'dh', 'hd', 'db', 'pb', 'pn', 'rc', 'rp', 'rq', 'ry', 'id', 'iv', 'iz', 'in', 'iw', 'gg', 'ta', 'qo', 'dq', 'qq',
  'zt', 'kz', 'io',
  'd', 'v', 'z', 't', 'k', 'o', 'a', 'm', 'c', 'g', 'p', 'q', 'y', 'b', 'h', 'n', 'w', 'j',
];

const ROLL_CHARS = new Set([...'0123456789', 'i', 's', 'f']);   // digits + spin/flick (i marks inverted spin/flick)

/// Split a sequence string into ordered tokens, keeping "quoted comments" whole and never splitting inside () or [].
export function splitTokens(seq) {
  const out = [];
  let buf = '';
  let depth = 0;
  let inQuote = false;
  for (const ch of seq) {
    if (inQuote) { buf += ch; if (ch === '"') inQuote = false; continue; }
    if (ch === '"') { buf += ch; inQuote = true; continue; }
    if (ch === '(' || ch === '[') depth += 1;
    if (ch === ')' || ch === ']') depth = Math.max(0, depth - 1);
    if (/\s/.test(ch) && depth === 0) { if (buf) { out.push(buf); buf = ''; } continue; }
    buf += ch;
  }
  if (buf) out.push(buf);
  return out;
}

/// Locate the base figure inside a token: the longest BASE_FIGURES entry, at the earliest position that isn't a
/// leading roll/entry run. Returns { base, at } or { base: '', at: -1 } for a rolling line (e.g. "1", "2").
function findBase(token) {
  for (let i = 0; i < token.length; i += 1) {
    for (const base of BASE_FIGURES) {   // BASE_FIGURES is longest-first, so the first hit is the greediest
      if (token.startsWith(base, i)) return { base, at: i };
    }
  }
  return { base: '', at: -1 };
}

/// Structure one figure token. `raw` round-trips exactly; the rest is best-effort for the catalogue/drawing.
export function parseFigure(raw) {
  let entryInverted = false;
  let body = raw;
  if (body.startsWith('-')) { entryInverted = true; body = body.slice(1); }   // inverted entry
  const { base, at } = findBase(body);
  if (at < 0) {
    return { raw, kind: 'figure', entryInverted, base: '', prefix: body, suffix: '', rolls: extractRolls(body) };
  }
  const prefix = body.slice(0, at);          // prefix rolls (digits) before the base
  const suffix = body.slice(at + base.length);  // postfix rolls, (positioned) rolls, direction/line modifiers
  return {
    raw, kind: 'figure', entryInverted, base, prefix, suffix,
    reverse: base.startsWith('r'),
    inverted: base.startsWith('i'),
    rolls: [...extractRolls(prefix), ...extractRolls(suffix)],
  };
}

/// Pull out roll/spin/flick groups from a fragment: runs of digits optionally followed by s/f (with i for inverted),
/// and any (parenthesised) positioned groups. Kept coarse on purpose — aresti.js interprets exact meaning.
function extractRolls(frag) {
  const rolls = [];
  const re = /\((.*?)\)|(i?\d*[sf])|(\d+)/g;   // (group) | spin/flick | plain roll digits
  let m;
  while ((m = re.exec(frag))) {
    if (m[1] !== undefined) rolls.push({ code: m[1], positioned: true });
    else rolls.push({ code: m[2] || m[3], positioned: false });
  }
  return rolls;
}

/// Parse a whole sequence string into ordered items (figures, comments, meta like "@A" tags or moves).
export function parseSequence(seq) {
  return splitTokens(seq).map((tok) => {
    if (tok.startsWith('"')) return { raw: tok, kind: 'comment', text: tok.replace(/^"|"$/g, '') };
    if (/^[\[(]/.test(tok) || tok.endsWith('%') || tok.startsWith('/') || /^e[duj]/.test(tok)) {
      return { raw: tok, kind: 'meta' };   // moves, size, axis, entry-direction — carried but not a scored figure
    }
    return parseFigure(tok);
  });
}

/// Serialize parsed items back to a sequence string. Exact round-trip: every item carries its raw text.
export function sequenceToString(items) {
  return items.map((it) => it.raw).join(' ');
}

/// The scored figures of a sequence, in order (drops comments and meta tokens).
export function figures(items) {
  return items.filter((it) => it.kind === 'figure');
}
