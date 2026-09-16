// One length unit for the whole app (ft or m), persisted. Internals stay in SI / the wire's units;
// conversion happens only at the display and input edges.
import { getItem, setItem } from './storage.js';

export const FT_TO_M = 0.3048;
const FIGURE_SPACE = ' ';
export let unit = getItem('acroReplay.units') === 'm' ? 'm' : 'ft';

export function setUnit(u) {
  unit = u === 'm' ? 'm' : 'ft';
  setItem('acroReplay.units', unit);
}
export const mToUnit = (m) => (unit === 'ft' ? m / FT_TO_M : m);
export const unitToM = (v) => (unit === 'ft' ? v * FT_TO_M : v);
export const ftToUnit = (ft) => (unit === 'ft' ? ft : ft * FT_TO_M);
export const unitToFt = (v) => (unit === 'ft' ? v : v / FT_TO_M);

// Constant-width readout: value padded to `digits` figure spaces, e.g. "  652 ft".
export function fmtLenFixed(m, digits = 4) {
  return `${String(Math.round(mToUnit(m))).padStart(digits, FIGURE_SPACE)} ${unit}`;
}
export function fmtLen(m) {
  return `${Math.round(mToUnit(m))} ${unit}`;
}
