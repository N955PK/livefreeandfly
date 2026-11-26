// Turbo Snow offline support. Keeps the page, the map code, and every region's terrain on the phone so the page still
// opens with no signal. The page is fetched fresh whenever there's signal (falling back to the saved copy after a
// few seconds on a weak one). The forecast itself isn't cached here: the page keeps its own copy of the index and of
// each region it loaded. Road status is never saved, so it is never shown stale. The page keeps the last
// avalanche forecast it read as well, and marks it as a saved copy when it shows it without a signal.
// Bump VERSION to drop old copies.
const VERSION = 'sierra-snow-v75';
const THREE = 'https://cdn.jsdelivr.net/npm/three@0.160.0/';
const SHELL = ['./', 'map3d.js', 'manifest.webmanifest', 'icons/mark.svg', 'icons/mark-white.svg', 'icons/icon-192.png',
  'data/terrain.json', 'data/terrain.bin', 'data/roads.json',
  'data/terrain-mammoth.json?v=4', 'data/terrain-mammoth.bin?v=4', 'data/roads-mammoth.json?v=4',
  'data/terrain-newengland.json?v=2', 'data/terrain-newengland.bin?v=2', 'data/roads-newengland.json?v=2',
  'data/terrain-seattle.json?v=2', 'data/terrain-seattle.bin?v=2', 'data/terrain-seattle.water.bin?v=2', 'data/roads-seattle.json?v=2',
  'data/terrain-tetons.json', 'data/terrain-tetons.bin', 'data/terrain-tetons.water.bin', 'data/roads-tetons.json',
  'data/terrain-wasatch.json?v=2', 'data/terrain-wasatch.bin?v=2', 'data/terrain-wasatch.water.bin?v=2', 'data/roads-wasatch.json?v=2',
  'data/terrain-colorado.json', 'data/terrain-colorado.bin', 'data/roads-colorado.json',
  'data/terrain-shasta.json', 'data/terrain-shasta.bin', 'data/roads-shasta.json',
  'data/terrain-okanagan.json', 'data/terrain-okanagan.bin', 'data/roads-okanagan.json',
  'data/terrain-bccoast.json?v=2', 'data/terrain-bccoast.bin?v=2', 'data/roads-bccoast.json?v=2',
  'data/terrain-quebec.json?v=2', 'data/terrain-quebec.bin?v=2', 'data/roads-quebec.json?v=2',
  'data/terrain-powderhighway.json', 'data/terrain-powderhighway.bin', 'data/roads-powderhighway.json',
  'data/terrain-eastkootenays.json?v=2', 'data/terrain-eastkootenays.bin?v=2', 'data/roads-eastkootenays.json?v=2',
  'data/terrain-rockies.json', 'data/terrain-rockies.bin', 'data/roads-rockies.json',
  'data/terrain-montana.json', 'data/terrain-montana.bin', 'data/roads-montana.json',
  'data/terrain-sunvalley.json', 'data/terrain-sunvalley.bin', 'data/roads-sunvalley.json',
  'data/terrain-oregon.json', 'data/terrain-oregon.bin', 'data/roads-oregon.json',
  'data/terrain-newmexico.json', 'data/terrain-newmexico.bin', 'data/roads-newmexico.json',
  'data/terrain-alaska.json', 'data/terrain-alaska.bin', 'data/roads-alaska.json',
  'data/terrain-swcolorado.json?v=2', 'data/terrain-swcolorado.bin?v=2', 'data/roads-swcolorado.json?v=2',
  'data/terrain-westidaho.json', 'data/terrain-westidaho.bin', 'data/roads-westidaho.json',
  'data/terrain-wyoming.json', 'data/terrain-wyoming.bin', 'data/roads-wyoming.json',
  'data/terrain-southutah.json', 'data/terrain-southutah.bin', 'data/roads-southutah.json',
  'data/terrain-arizona.json', 'data/terrain-arizona.bin', 'data/roads-arizona.json',
  'data/terrain-lasvegas.json', 'data/terrain-lasvegas.bin', 'data/roads-lasvegas.json',
  'data/terrain-socal.json', 'data/terrain-socal.bin', 'data/roads-socal.json',
  'data/terrain-juneau.json', 'data/terrain-juneau.bin', 'data/roads-juneau.json',
  'data/terrain-valdez.json', 'data/terrain-valdez.bin', 'data/roads-valdez.json',
  'data/terrain-inlandnw.json', 'data/terrain-inlandnw.bin', 'data/roads-inlandnw.json',
  'data/terrain-nwmontana.json', 'data/terrain-nwmontana.bin', 'data/roads-nwmontana.json',
  'data/terrain-newyork.json', 'data/terrain-newyork.bin', 'data/roads-newyork.json',
  'data/terrain-midatlantic.json', 'data/terrain-midatlantic.bin', 'data/roads-midatlantic.json',
  'data/terrain-lakesuperior.json', 'data/terrain-lakesuperior.bin', 'data/roads-lakesuperior.json',
  'data/terrain-michigan.json', 'data/terrain-michigan.bin', 'data/roads-michigan.json',
  'data/terrain-blackhills.json', 'data/terrain-blackhills.bin', 'data/roads-blackhills.json',
  'data/terrain-northbc.json', 'data/terrain-northbc.bin', 'data/roads-northbc.json',
  'data/terrain-ontario.json', 'data/terrain-ontario.bin', 'data/roads-ontario.json',
  'data/terrain-gaspesie.json', 'data/terrain-gaspesie.bin', 'data/roads-gaspesie.json',
  'data/terrain-newfoundland.json', 'data/terrain-newfoundland.bin', 'data/roads-newfoundland.json',
  'data/terrain-yukon.json', 'data/terrain-yukon.bin', 'data/roads-yukon.json'];
const MODULES = [THREE + 'build/three.module.js', THREE + 'examples/jsm/controls/OrbitControls.js'];
const PAGE_TIMEOUT_MS = 4000;
// The avalanche centers' artwork, kept so a saved forecast still shows its signs with no signal: the six danger-scale
// signs, and the drawing for each kind of avalanche problem. They never change, so the saved copy is always used.
const SIGNS = 'https://nac-web-platforms.s3.us-west-1.amazonaws.com/assets/danger-icons/';
const PROBLEMS = 'https://api.avalanche.org/img/avalanche_problems/';
// The forecasters' photographs. The page saves the ones it shows (in its own store, which it empties whenever it
// takes a new set of forecasts); here they are only served from that store when it has them.
const PHOTOS = 'https://avalanche-org-media.s3.us-west-2.amazonaws.com/', PHOTO_STORE = 'sierra-snow-avy';
const ARTWORK = [...[0, 1, 2, 3, 4, 5].map((level) => `${SIGNS}${level}.png`),
  ...['DryLoose', 'StormSlab', 'WindSlab', 'PersistentSlab', 'DeepPersistentSlab', 'WetLoose', 'WetSlab', 'Cornice', 'Glide'].map((name) => `${PROBLEMS}${name}.png`)];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    // One missing file must not stop the rest from being saved.
    await Promise.all([...SHELL, ...MODULES.map((url) => new Request(url, { mode: 'cors' }))]
      .map((item) => c.add(item).catch(() => {})));
    // Another site's pictures can be saved but not read, so they are stored as they come (c.add would refuse them).
    await Promise.all(ARTWORK.map((url) => fetch(new Request(url, { mode: 'no-cors' })).then((res) => c.put(url, res)).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith('sierra-snow-v') && k !== VERSION) await caches.delete(k);
    await self.clients.claim();
  })());
});

async function pageFirst(req) {
  const c = await caches.open(VERSION);
  const net = fetch(req).then((res) => { if (res.ok) c.put('./', res.clone()); return res; });
  const timeout = new Promise((ok) => setTimeout(ok, PAGE_TIMEOUT_MS));
  const fast = await Promise.race([net.catch(() => null), timeout]);
  if (fast) return fast;
  const saved = await c.match('./');
  return saved || net;
}

// A file whose address carries a version (map3d.js?v=84) must match the page that asked for it, so only that exact
// copy is served from the phone; with no signal, any saved copy is better than none. Files without a version are
// served from the phone and refreshed in the background.
async function savedFirst(req) {
  const c = await caches.open(VERSION);
  const versioned = new URL(req.url).search !== '';
  const saved = await c.match(req);
  const net = fetch(req).then((res) => { if (res.ok) c.put(req, res.clone()); return res; });
  if (saved) { if (versioned) return saved; net.catch(() => {}); return saved; }
  try { return await net; } catch (error) {
    const any = await c.match(req, { ignoreSearch: true });
    if (any) return any;
    throw error;
  }
}

// A picture that never changes: the saved copy if there is one, otherwise fetched and saved for next time.
async function keptPicture(req) {
  const c = await caches.open(VERSION);
  const saved = await c.match(req.url);
  if (saved) return saved;
  const res = await fetch(req);
  if (res.ok || res.type === 'opaque') c.put(req.url, res.clone());
  return res;
}

async function savedPhoto(req) {
  const saved = await (await caches.open(PHOTO_STORE)).match(req.url);
  return saved || fetch(req);
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url), scope = new URL(self.registration.scope);
  if (req.mode === 'navigate' && url.origin === location.origin
      && (url.pathname === scope.pathname || url.pathname === scope.pathname + 'index.html')) {
    return e.respondWith(pageFirst(req));
  }
  // The local forecast files are only used when developing; the published ones come from another site.
  if (url.origin === location.origin && (url.pathname === scope.pathname + 'data/forecast.json'
      || url.pathname === scope.pathname + 'data/index.json' || url.pathname.startsWith(scope.pathname + 'data/forecast/')
      || url.pathname.startsWith(scope.pathname + 'data/canada/'))) return;
  if (url.href.startsWith(SIGNS) || url.href.startsWith(PROBLEMS)) return e.respondWith(keptPicture(req));
  if (url.href.startsWith(PHOTOS)) return e.respondWith(savedPhoto(req));
  if ((url.origin === location.origin && url.pathname.startsWith(scope.pathname)) || url.href.startsWith(THREE)) {
    return e.respondWith(savedFirst(req));
  }
});
