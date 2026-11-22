// Turbo Snow offline support. Keeps the page, the map code, and both terrain sets on the phone so the page still
// opens with no signal. The page is fetched fresh whenever there's signal (falling back to the saved copy after a
// few seconds on a weak one). The forecast itself isn't cached here: the page keeps its own copy of the last one
// it loaded. Road status is never saved, so it is never shown stale. The page keeps the last
// avalanche forecast it read as well, and marks it as a saved copy when it shows it without a signal.
// Bump VERSION to drop old copies.
const VERSION = 'sierra-snow-v4';
const THREE = 'https://cdn.jsdelivr.net/npm/three@0.160.0/';
const SHELL = ['./', 'map3d.js', 'manifest.webmanifest', 'icons/mark.png', 'icons/mark-white.png?v=2', 'icons/icon-192.png',
  'data/terrain.json', 'data/terrain.bin', 'data/roads.json',
  'data/terrain-mammoth.json?v=3', 'data/terrain-mammoth.bin?v=3', 'data/roads-mammoth.json?v=3'];
const MODULES = [THREE + 'build/three.module.js', THREE + 'examples/jsm/controls/OrbitControls.js'];
const PAGE_TIMEOUT_MS = 4000;

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    // One missing file must not stop the rest from being saved.
    await Promise.all([...SHELL, ...MODULES.map((url) => new Request(url, { mode: 'cors' }))]
      .map((item) => c.add(item).catch(() => {})));
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

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url), scope = new URL(self.registration.scope);
  if (req.mode === 'navigate' && url.origin === location.origin
      && (url.pathname === scope.pathname || url.pathname === scope.pathname + 'index.html')) {
    return e.respondWith(pageFirst(req));
  }
  // The local forecast file is only used when developing; the published one comes from another site.
  if (url.origin === location.origin && url.pathname === scope.pathname + 'data/forecast.json') return;
  if ((url.origin === location.origin && url.pathname.startsWith(scope.pathname)) || url.href.startsWith(THREE)) {
    return e.respondWith(savedFirst(req));
  }
});
