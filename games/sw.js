// Ace's service worker. It is here so a phone can show
// "your turn" while the game is closed. The sender (games/push) delivers {title, body, url, tag}.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
// The score pad has to open at a table with no signal. Its page and the few files it needs are fetched as usual
// when there is a connection (and the copy kept is refreshed); with none, the kept copy answers. Nothing else in
// the room is kept: the games themselves need the card room anyway.
const PAD = 'ace-pad-v1';
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (!/^\/games\/(score\/(index\.html)?$|room\.css$|icons\/)/.test(url.pathname)) return;
  event.respondWith(fetch(event.request).then((reply) => {
    if (reply.ok) { const copy = reply.clone(); caches.open(PAD).then((c) => c.put(event.request, copy)); }
    return reply;
  }).catch(() => caches.match(event.request, { ignoreSearch: true }).then((kept) => kept || Response.error())));
});
self.addEventListener('push', (event) => {
  let note = {};
  try { note = event.data.json(); } catch (e) { /* a message with nothing in it still has to show something */ }
  event.waitUntil(self.registration.showNotification(note.title || 'Ace', {
    body: note.body || 'Something happened at your table.', tag: note.tag || 'ace', renotify: true,
    icon: '/games/icons/icon-180.png', badge: '/games/icons/favicon-32.png', data: { url: note.url || '/games/' }
  }));
});
// Tapping it goes to the table: the window already open on it if there is one, else a new one.
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || '/games/', self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
    const open = windows.find((w) => w.url === url) || windows.find((w) => w.url.startsWith(self.location.origin + '/games/'));
    if (open) return (open.url === url ? Promise.resolve(open) : open.navigate(url).catch(() => open)).then((w) => (w || open).focus());
    return self.clients.openWindow(url);
  }));
});
