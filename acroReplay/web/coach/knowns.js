// The 2026 IAC Power Known sequences. The sequence data itself lives in the vendored OpenAero library
// (data/library.js), keyed by these names; oadraw.renderLibrary(key) loads and draws each straight from OpenAero, so
// there is no fragile transcription of the (very formatting-heavy) OLAN strings here. K and figure counts are cached
// for the menu — OpenAero remains the source of truth at render time.
export const POWER_KNOWNS_2026 = [
  { key: '2026 IAC Primary Known', category: 'Primary', k: 58, figs: 6 },
  { key: '2026 IAC Sportsman Known', category: 'Sportsman', k: 127, figs: 11 },
  { key: '2026 IAC Intermediate Known', category: 'Intermediate', k: 180, figs: 11 },
  { key: '2026 IAC Advanced Known', category: 'Advanced', k: 285, figs: 11 },
  { key: '2026 IAC Unlimited Known', category: 'Unlimited', k: 395, figs: 10 },
];
