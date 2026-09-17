// Aresti catalogue: resolve a parsed OLAN figure (from olan.js) to its name, Aresti catalogue number and K-factor.
// Clean-room — the data are facts transcribed from the FAI Aresti catalogue and the official IAC Known PDFs, not
// copied from OpenAero's GPL database. K here is the competition (power) K-factor.
//
// FIGURES holds fully-resolved figures keyed by their exact OLAN token; it grows as each category's Known sequence is
// transcribed. BASE_FIGURE gives every base figure an identity (name + Aresti family) so a figure can still be named
// and drawn — for imports and the flown-to-Aresti reverse — before its exact K has been entered.

// Aresti families (the top digit of a catalogue number).
export const FAMILY = {
  1: 'lines', 2: 'turns & rolling turns', 5: 'hammerheads', 6: 'tailslides',
  7: 'loops & part-loops', 8: 'loop & line combinations', 9: 'rolls, snaps & spins',
};

// Fully-resolved figures, keyed by exact OLAN token. Seeded with the IAC Primary Known (2026) — Aresti numbers and
// K-factors from the sequence card; composite entries (line/loop base + roll) show both catalogue numbers.
export const FIGURES = {
  d: { name: '45° up line', aresti: '1.1.2.1', k: 7 },
  iv6s: { name: '1½-turn upright spin, vertical down line', aresti: '1.1.6.3 + 9.11.1.6', k: 13 },
  c2: { name: 'half Cuban, ½ roll on the 45° down line', aresti: '8.5.2.1 + 9.1.3.2', k: 14 },
  o: { name: 'loop', aresti: '7.4.1.1', k: 10 },
  '2j': { name: '180° competition turn', aresti: '2.2.1.1', k: 4 },
  '1': { name: 'slow roll (one full roll)', aresti: '1.1.1.1 + 9.1.3.4', k: 10 },
};

// Base-figure identity for naming and drawing any parsed figure. `family` is the Aresti family number.
export const BASE_FIGURE = {
  o: { name: 'loop', family: 7 }, io: { name: 'outside loop', family: 7 },
  a: { name: 'split-S', family: 7 }, m: { name: 'Immelmann', family: 7 },
  qo: { name: 'square loop', family: 7 }, dq: { name: 'diamond loop', family: 7 },
  c: { name: 'half Cuban', family: 8 }, rc: { name: 'reverse half Cuban', family: 8 },
  g: { name: 'goldfish', family: 8 }, gg: { name: 'double goldfish', family: 8 },
  p: { name: 'P-loop', family: 8 }, rp: { name: 'reverse P-loop', family: 8 },
  q: { name: 'Q-loop', family: 8 }, rq: { name: 'reverse Q-loop', family: 8 },
  y: { name: 'keyhole', family: 8 }, ry: { name: 'reverse keyhole', family: 8 },
  b: { name: 'humpty bump', family: 8 }, pb: { name: 'push humpty bump', family: 8 },
  n: { name: 'N figure', family: 8 }, pn: { name: 'push-N figure', family: 8 }, w: { name: 'bow-tie', family: 8 },
  d: { name: '45° up line', family: 1 }, id: { name: '45° down line', family: 1 },
  v: { name: 'vertical up line', family: 1 }, iv: { name: 'vertical down line', family: 1 },
  z: { name: 'Z figure', family: 1 }, t: { name: 'shark-tooth (tooth)', family: 1 }, k: { name: 'shark-tooth', family: 1 },
  j: { name: 'turn', family: 2 },
  h: { name: 'hammerhead', family: 5 }, dh: { name: 'hammerhead, diagonal entry', family: 5 },
  hd: { name: 'hammerhead, diagonal exit', family: 5 }, dhd: { name: 'hammerhead, diagonal entry & exit', family: 5 },
  ta: { name: 'tailslide', family: 6 }, ita: { name: 'inverted tailslide', family: 6 },
};

/// Resolve a parsed figure (olan.js parseFigure output) to { name, aresti, k, family, olan, exact }.
/// `exact:true` when the figure's exact catalogue entry is known; otherwise name/family come from the base figure
/// and k/aresti are null (to be transcribed) — never guessed.
export function resolve(fig) {
  const hit = FIGURES[fig.raw];
  if (hit) return { ...hit, family: Number(hit.aresti[0]), olan: fig.raw, exact: true };
  const b = BASE_FIGURE[fig.base];
  const name = b ? b.name : (fig.base ? fig.base : 'rolling line');
  const rollNote = fig.rolls.length ? ` + ${fig.rolls.length} roll${fig.rolls.length === 1 ? '' : 's'}` : '';
  return { name: name + rollNote, aresti: null, k: null, family: b ? b.family : null, olan: fig.raw, exact: false };
}

/// Total K of a resolved figure list; { k, complete } where complete is false if any figure lacked an exact K.
export function sequenceK(resolved) {
  let k = 0; let complete = true;
  for (const r of resolved) { if (r.k == null) complete = false; else k += r.k; }
  return { k, complete };
}
