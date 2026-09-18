// Turn the app's detected/graded figures (judge.js output: { type, measurements }) into an OLAN sequence string, so a
// flown flight can be drawn as Aresti via oadraw/OpenAero — the "make an Aresti from what was flown" direction.
// Best-effort: maps the recognised figure types and their key parameters (spin turns, roll extent, turn degrees) to
// OLAN tokens; unrecognised figures are dropped.

// OLAN rotation digit for a number of turns (1 = full, 2 = ½, 3 = ¾, 4 = ¼, 5 = 1¼, 6 = 1½, 7 = 1¾, 9 = 2).
const ROT = { 0.25: '4', 0.5: '2', 0.75: '3', 1: '1', 1.25: '5', 1.5: '6', 1.75: '7', 2: '9' };
function rotDigit(turns) {
  const t = Math.round((turns || 0) / 0.25) * 0.25;
  if (t <= 0) return '';
  return ROT[t] || (t >= 2 ? '9' : '1');
}
function turnToken(deg) {
  const q = Math.max(1, Math.min(4, Math.round(Math.abs(deg || 180) / 90)));   // 90°→j, 180°→2j, 270°→3j, 360°→4j
  return q === 1 ? 'j' : `${q}j`;
}

/// One graded figure → its OLAN token (or '' if not mappable).
export function figureToOlan(g) {
  if (!g || !g.type) return '';
  const m = g.measurements || {};
  switch (g.type) {
    case 'loop': return 'o';
    case '45 up line': return (m.lineDeg < 0 ? 'id' : 'd');
    case '180 turn': return turnToken(m.turnDeg);
    case 'slow roll': return rotDigit((m.extentDeg || 360) / 360) || '1';
    case 'half cuban': return `c${m.rollDeg ? rotDigit(m.rollDeg / 360) : ''}`;
    case 'spin': return `${rotDigit(m.turns) || '1'}s`;
    default: return '';
  }
}

/// A list of graded figures → an OLAN sequence string for drawing.
export function flownToOlan(figures) {
  return (figures || []).map(figureToOlan).filter(Boolean).join(' ');
}
