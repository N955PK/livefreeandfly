// ski/lease offline support. Keeps the page and its files on the phone so it still opens with no signal at the house.
// The page is fetched fresh whenever there's signal (falling back to the saved copy after a few seconds on a weak one);
// everything else is served from the saved copy and refreshed in the background. House data isn't cached here:
// the page keeps its own copy of the last data it loaded. Bump VERSION to drop old copies.
const VERSION = 'ski-lease-v1';
const SUPABASE_JS = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js';
const SHELL = ['./', 'qrcode.js', 'manifest.webmanifest', 'skier-mark.png', 'icon-32.png', 'icon-180.png', 'icon-192.png', 'icon-512.png', 'privacy.html'];
const PAGE_TIMEOUT_MS = 4000;

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    await c.addAll(SHELL);
    try { await c.add(new Request(SUPABASE_JS, { mode: 'cors' })); } catch (err) { /* cached on first use instead */ }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith('ski-lease-') && k !== VERSION) await caches.delete(k);
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

async function savedFirst(req) {
  const c = await caches.open(VERSION);
  const saved = await c.match(req, { ignoreSearch: true });
  const net = fetch(req).then((res) => { if (res.ok) c.put(req, res.clone()); return res; });
  if (saved) { net.catch(() => {}); return saved; }
  return net;
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url), scope = new URL(self.registration.scope);
  if (req.mode === 'navigate' && url.origin === location.origin
      && (url.pathname === scope.pathname || url.pathname === scope.pathname + 'index.html')) {
    return e.respondWith(pageFirst(req));
  }
  if ((url.origin === location.origin && url.pathname.startsWith(scope.pathname)) || url.href === SUPABASE_JS) {
    return e.respondWith(savedFirst(req));
  }
});
