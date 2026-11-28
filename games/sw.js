// game/room's service worker. It keeps nothing and answers no page loads; it is here only so a phone can show
// "your turn" while the game is closed. The sender (games/push) delivers {title, body, url, tag}.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('push', (event) => {
  let note = {};
  try { note = event.data.json(); } catch (e) { /* a message with nothing in it still has to show something */ }
  event.waitUntil(self.registration.showNotification(note.title || 'game/room', {
    body: note.body || 'Something happened at your table.', tag: note.tag || 'game-room', renotify: true,
    icon: '/assets/apple-touch-icon.v13.png', badge: '/assets/favicon-32.v13.png', data: { url: note.url || '/games/' }
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
