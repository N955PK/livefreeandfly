/* game/room: what every page in the room shares. Who you are, the calls to the card room, the lists of tables,
   live nudges between two pages, and sound. A game's page loads this and adds its own table.

   The room runs on the same Supabase project as ski/lease (games/sql). A player is this browser: the room hands it a
   long random key the first time it does anything, and the key goes along with every call after that. The key is
   the publishable one and is safe to ship. On localhost the pages talk to games/dev/server.py instead. */
window.Room = (() => {
'use strict';

const CONFIG = {
  supabaseUrl: 'https://lzbvkrqdrizgnwpbname.supabase.co',
  supabaseAnonKey: 'sb_publishable_AfcKk4cO5zTDNSsZThrRHA_kLq8YzYa'
};
const SUPABASE_JS = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js';
// The browser refuses the file if its contents ever differ from this hash. Update both together when bumping the version.
const SUPABASE_SRI = 'sha384-0w2KAL2YHP6wKOkUDzkCDGgVvfmHnj02DHeQ6XcHOgTfFsGyonKOpShMH1x6nk9o';
const DEV = ['localhost', '127.0.0.1'].includes(location.hostname);
const API = DEV ? location.origin : CONFIG.supabaseUrl.replace(/\/$/, '');

// Every game in the room. The lists use this to name a table and say how it's going; add a game here and it shows up.
const GAMES = {
  gin: {
    name: 'gin/rummy', path: '/games/gin/',
    options: (o) => (o.mode === 'hollywood' ? 'Hollywood to ' : 'Single game to ') + o.target +
      (+o.cents > 0 ? ' · ' + (+o.cents < 100 ? +o.cents + '¢' : '$' + (o.cents / 100).toFixed(2)) + ' a point' : ''),
    score(t) {
      const tot = t.summary && t.summary.totals;
      if (!tot || t.status === 'waiting') return '';
      const n = t.options.mode === 'hollywood' ? 3 : 1;
      return tot.slice(0, n).map((g) => `${g[t.seat]}–${g[1 - t.seat]}`).join(' · ');
    },
    idle: (t) => (t.summary && t.summary.state === 'hand_over' ? 'DEAL' : 'THEIR TURN')
  }
};

const FACES = ['🦊','🐻','🦉','🐙','🦄','🐸','🐼','🦁','🐯','🐶','🐱','🦖','🐳','🦅','🐝','🦩',
               '🛩️','🚁','🪂','⛷️','🏔️','🎿','🤠','😎','🤖','👽','👻','🎩','🃏','🎲','🔥','🍀'];
const COLORS = ['#a31f34','#39d0a4','#3aa8ff','#ffa32e','#d95ce8','#e8d34f','#8f9bff','#ff5c39','#5fd0e8','#b5e05a','#ff8fb1','#5b6b7a'];

/* ---------- small helpers ---------- */
const $ = (s, r) => (r || document).querySelector(s);
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === 'class') el.className = v; else if (k === 'on') for (const [e, f] of Object.entries(v)) el.addEventListener(e, f);
    else if (k === 'style') el.style.cssText = v; else if (v !== false && v != null) el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid);
  return el;
}
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private window: carry on without it */ } },
  del(k) { try { localStorage.removeItem(k); } catch (e) { /* nothing to remove */ } },
  keys() { try { return Object.keys(localStorage); } catch (e) { return []; } }
};
let toastTimer;
function toast(msg) {
  let t = $('#toast');
  if (!t) { t = h('div', { id: 'toast', role: 'status', 'aria-live': 'polite' }); document.body.append(t); }
  const top = [...document.querySelectorAll('dialog[open]')].pop();     // an open dialog sits above the page
  (top || document.body).append(t);
  t.textContent = msg; t.classList.add('on');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('on'), 3200);
}
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;

/* ---------- talking to the card room ---------- */
async function rpc(fn, args) {
  let res;
  try {
    res = await fetch(`${API}/rest/v1/rpc/${fn}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', apikey: CONFIG.supabaseAnonKey, Authorization: 'Bearer ' + CONFIG.supabaseAnonKey },
      body: JSON.stringify(args || {})
    });
  } catch (e) { throw new Error('No connection. Trying again…'); }
  const body = await res.json().catch(() => null);
  if (res.ok) return body;
  if (res.status === 404 || (body && body.code === 'PGRST202')) throw new Error('The game room is being set up. Try again in a little while.');
  throw new Error((body && body.message) || 'Something went wrong');
}

/* ---------- who you are ---------- */
const KEY = 'lff-games-key', PROFILE = 'lff-games-profile', SYNCED = 'lff-games-synced', HANDLE = 'lff-games-handle';
const pickOne = (list) => list[Math.floor(Math.random() * list.length)];
const profile = Object.assign({ name: '', avatar: pickOne(FACES), color: pickOne(COLORS) }, store.get(PROFILE, {}));
let key = store.get(KEY, null);
let handle = store.get(HANDLE, null);     // the login name of the account this browser is logged in to, if any
const saveProfile = () => store.set(PROFILE, profile);
const signature = () => JSON.stringify([profile.name, profile.avatar, profile.color]);

// This browser's key, making sure the room knows it and has the current name and face.
let hello = null;
function me() {
  if (key && store.get(SYNCED) === signature()) return Promise.resolve(key);
  hello = hello || (async () => {
    try {
      const sig = signature();
      const r = await rpc('room_hello', { p_token: key, p_name: profile.name, p_avatar: profile.avatar, p_color: profile.color });
      key = r.token; store.set(KEY, key); store.set(SYNCED, sig);
      return key;
    } finally { hello = null; }
  })();
  return hello;
}
// A call made as you. If the room has forgotten this browser (it sweeps out keys unused for months), it's
// introduced again and the call is retried once.
async function call(fn, args) {
  try { return await rpc(fn, { p_token: await me(), ...args }); }
  catch (e) {
    if (!/doesn.t know this browser/.test(e.message)) throw e;
    key = null; store.del(KEY); store.del(SYNCED);
    return rpc(fn, { p_token: await me(), ...args });
  }
}
function named() {
  if (profile.name.trim()) return true;
  toast('What should we call you?');
  const box = [...document.querySelectorAll('.who input')].find((el) => el.offsetParent);
  if (box) box.focus();
  return false;
}

// Before any page does anything: take over a key handed across from another device (?me=...), and gather up seats
// from the first version of gin, which kept a separate key per table.
const ready = (async () => {
  const url = new URL(location.href), incoming = url.searchParams.get('me');
  if (incoming) {
    url.searchParams.delete('me');
    history.replaceState(null, '', url);
    try {
      const who = await rpc('room_who', { p_token: incoming });
      if (key && key !== incoming) await rpc('room_adopt', { p_token: incoming, p_other: key }).catch(() => {});
      key = incoming; store.set(KEY, key);
      handle = who.handle || null; if (handle) store.set(HANDLE, handle); else store.del(HANDLE);
      Object.assign(profile, { name: who.name, avatar: who.avatar, color: who.color }); saveProfile(); store.set(SYNCED, signature());
      toast(`This device is now playing as ${who.name}.`);
    } catch (e) { toast('That link didn’t work. Make a new one on your other device.'); }
  }
  // Whether this browser's key is an account's is asked once a visit, so a login made elsewhere with a link shows.
  if (key && !incoming) {
    try { const who = await rpc('room_who', { p_token: key }); handle = who.handle || null; if (handle) store.set(HANDLE, handle); else store.del(HANDLE); }
    catch (e) { /* an older room, or no signal: what this browser remembers stands */ }
  }
  const old = store.keys().filter((k) => k.startsWith('gin-seat-'));
  if (old.length) {
    try {
      const mine = await me();
      for (const k of old) {
        const other = store.get(k, null);
        if (typeof other === 'string' && other !== mine) await rpc('room_adopt', { p_token: mine, p_other: other });
        store.del(k);
      }
    } catch (e) { /* the old keys stay put and this runs again next time */ }
  }
})();

function avatarEl(face, cls) {
  const el = h('div', { class: 'av' + (cls ? ' ' + cls : '') });
  setAvatar(el, face);
  return el;
}
function setAvatar(el, face) {
  el.classList.toggle('empty', !face);
  el.textContent = face ? face.avatar || '🃏' : '?';
  el.style.setProperty('--c', (face && face.color) || '#a31f34');
}
// Name box, face grid, and color dots. Edits p in place and calls changed() after each one.
function profileEditor(box, p, changed) {
  const face = avatarEl(p, 'big');
  const name = h('input', { type: 'text', maxlength: 20, placeholder: 'Your name', value: p.name, autocomplete: 'nickname', 'aria-label': 'Your name',
    on: { input: () => { p.name = name.value; changed(); } } });
  const faces = h('div', { class: 'faces', role: 'group', 'aria-label': 'Avatar' }, FACES.map((f) =>
    h('button', { type: 'button', 'aria-pressed': String(f === p.avatar), on: { click: () => { p.avatar = f; sync(); } } }, f)));
  const dots = h('div', { class: 'swatches', role: 'group', 'aria-label': 'Color' }, COLORS.map((c) => {
    const b = h('button', { type: 'button', 'aria-label': c, 'aria-pressed': String(c === p.color), on: { click: () => { p.color = c; sync(); } } });
    b.style.setProperty('--c', c); b.dataset.c = c; return b;
  }));
  function sync() {
    setAvatar(face, p);
    [...faces.children].forEach((b) => b.setAttribute('aria-pressed', String(b.textContent === p.avatar)));
    [...dots.children].forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.c === p.color)));
    changed();
  }
  box.replaceChildren(h('div', { class: 'who' }, face, name), faces, dots);
}

/* ---------- dialogs any page can open ---------- */
function dialog(label, ...kids) {
  const d = h('dialog', { 'aria-label': label }, kids);
  d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
  d.addEventListener('close', () => d.remove());
  document.body.append(d); d.showModal();
  return d;
}
// Change your name and face. saved() runs once the room has them.
function profileDialog(saved) {
  const draft = { ...profile }, box = h('div', {});
  profileEditor(box, draft, () => {});
  const d = dialog('Your name and avatar', h('h3', {}, 'You'), h('div', { style: 'margin-top:14px' }, box), h('div', { class: 'btns' },
    h('button', { class: 'ghost', on: { click: () => d.close() } }, 'Cancel'),
    h('button', { class: 'go', on: { click: async () => {
      if (!draft.name.trim()) { toast('What should we call you?'); return; }
      Object.assign(profile, draft); saveProfile(); d.close();
      try { if (key) await me(); if (saved) saved(); } catch (e) { toast(e.message); }
    } } }, 'Save')));
}
let qrLib = null;
function qr(text) {
  qrLib = qrLib || new Promise((ok, no) => {
    if (window.qrcode) return ok();
    const s = h('script', { src: '/cabin/qrcode.js' });
    s.onload = () => ok(); s.onerror = () => { qrLib = null; no(new Error('qr')); };
    document.head.append(s);
  });
  return qrLib.then(() => {
    const q = window.qrcode(0, 'M'); q.addData(text); q.make();
    const box = h('div', { class: 'qr', role: 'img', 'aria-label': 'QR code' });
    box.innerHTML = q.createSvgTag({ scalable: true, margin: 2 });     // the library's own markup, built from our link
    return box;
  });
}
// Carry your seat at every table to another phone or laptop.
async function deviceDialog() {
  let link;
  try { link = `${location.origin}/games/?me=${await me()}`; } catch (e) { return toast(e.message); }
  const spot = h('div', {});
  dialog('Play on another device', h('h3', {}, 'Play on another device'),
    h('p', { class: 'why' }, 'Scan this with your other phone, or open the link there. It will sit in your seat at every table, alongside this device.'),
    spot, h('div', { class: 'link' }, link),
    h('p', { class: 'why' }, 'Keep it to yourself: anyone with this link can play your cards.'),
    h('div', { class: 'btns' }, h('button', { class: 'ghost', on: { click: async () => {
      try { await navigator.clipboard.writeText(link); toast('Link copied'); } catch (e) { toast('Press and hold the link to copy it'); }
    } } }, 'Copy the link')));
  qr(link).then((el) => spot.append(el)).catch(() => {});
}

/* ---------- accounts: a login name and a password, so your tables follow you to any device ---------- */
// Takes over this browser with an account's key (after logging in or signing up) and starts the page afresh.
function become(who) {
  key = who.token; store.set(KEY, key);
  Object.assign(profile, { name: who.name, avatar: who.avatar, color: who.color }); saveProfile(); store.set(SYNCED, signature());
  handle = who.handle || null; if (handle) store.set(HANDLE, handle); else store.del(HANDLE);
  location.reload();
}
// Logging out leaves the account and its tables where they are; this browser simply stops being that player.
function logout() {
  key = null; handle = null; store.del(KEY); store.del(SYNCED); store.del(HANDLE);
  location.reload();
}
function accountDialog(mode) {
  const signup = mode === 'signup';
  const name = h('input', { type: 'text', maxlength: 20, placeholder: 'Login name', autocomplete: 'username', autocapitalize: 'none', spellcheck: 'false', 'aria-label': 'Login name' });
  const pass = h('input', { type: 'password', maxlength: 72, placeholder: signup ? 'Password (6 or more characters)' : 'Password', autocomplete: signup ? 'new-password' : 'current-password', 'aria-label': 'Password' });
  const note = h('p', { class: 'why warn', role: 'alert' });
  const go = h('button', { class: 'go', on: { click: submit } }, signup ? 'Create the account' : 'Log in');
  async function submit() {
    const n = name.value.trim(), w = pass.value;
    note.textContent = '';
    if (!/^[A-Za-z0-9_]{3,20}$/.test(n)) { note.textContent = 'A login name is 3 to 20 letters, digits or underscores.'; return name.focus(); }
    if (w.length < 6) { note.textContent = 'A password is at least 6 characters.'; return pass.focus(); }
    if (signup && !profile.name.trim()) { profile.name = n; saveProfile(); }     // a name to show at the table
    go.disabled = true;
    try {
      const r = signup ? await call('room_register', { p_handle: n, p_password: w }) : await rpc('room_login', { p_handle: n, p_password: w, p_token: key });
      if (r.error) { note.textContent = r.error; go.disabled = false; return; }
      become(r);
    } catch (e) { note.textContent = e.message; go.disabled = false; }
  }
  for (const box of [name, pass]) box.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  const d = dialog(signup ? 'Create an account' : 'Log in', h('h3', {}, signup ? 'Create an account' : 'Log in'),
    h('p', { class: 'why' }, signup ? 'Pick a login name and a password. Your tables and your record are kept under them, and you can log in on any phone or computer to find them. Games between two players with accounts count on the leaderboard.'
      : 'Your tables and your record come with you. Anything you were playing in this browser as a guest is added to your account.'),
    h('div', { class: 'acctform' }, name, pass), note,
    h('div', { class: 'btns' }, h('button', { class: 'ghost', on: { click: () => d.close() } }, 'Cancel'), go),
    h('p', { class: 'why' }, signup ? 'There is no email on file, so a forgotten password cannot be reset. Pick one you will remember.' : ''));
  name.focus();
}
function passwordDialog() {
  const old = h('input', { type: 'password', maxlength: 72, placeholder: 'Current password', autocomplete: 'current-password', 'aria-label': 'Current password' });
  const fresh = h('input', { type: 'password', maxlength: 72, placeholder: 'New password (6 or more characters)', autocomplete: 'new-password', 'aria-label': 'New password' });
  const note = h('p', { class: 'why warn', role: 'alert' });
  const d = dialog('Change your password', h('h3', {}, 'Change your password'), h('div', { class: 'acctform' }, old, fresh), note,
    h('div', { class: 'btns' }, h('button', { class: 'ghost', on: { click: () => d.close() } }, 'Cancel'),
      h('button', { class: 'go', on: { click: async () => {
        if (fresh.value.length < 6) { note.textContent = 'A password is at least 6 characters.'; return; }
        try {
          const r = await call('room_password', { p_old: old.value, p_new: fresh.value });
          if (r.error) { note.textContent = r.error; return; }
          d.close(); toast('Password changed');
        } catch (e) { note.textContent = e.message; }
      } } }, 'Change it')));
  old.focus();
}
// The line under your name that says whether you are logged in, with the buttons to change that.
function accountBox(box) {
  const link = (label, fn) => h('button', { type: 'button', class: 'alink', on: { click: fn } }, label);
  box.className = 'acct';
  if (handle) box.replaceChildren(h('span', {}, 'Logged in as ', h('b', {}, handle)), link('Change password', passwordDialog), link('Log out', () => {
    const d = dialog('Log out', h('h3', {}, 'Log out?'), h('p', { class: 'why' }, 'Your tables and your record stay with your account. Log in again here or anywhere to get back to them.'),
      h('div', { class: 'btns' }, h('button', { class: 'ghost', on: { click: () => d.close() } }, 'Stay'), h('button', { class: 'go', on: { click: logout } }, 'Log out')));
  }));
  else box.replaceChildren(h('span', {}, 'Playing as a guest on this device.'), link('Log in', () => accountDialog('login')), link('Create an account', () => accountDialog('signup')));
  const state = pushState();
  if (state !== 'none') box.append(link(state === 'on' ? '🔔 Notifications on' : '🔔 Turn on notifications', () => pushDialog(() => accountBox(box))));
}
/* ---------- notifications: a buzz on the phone when the table is waiting on you ---------- */
// The sender is the "push" edge function (games/push); the list of devices is in the card room. An iPhone only
// allows this for a page added to the Home Screen and opened from there.
const PUSH_FN = DEV ? null : API + '/functions/v1/push', PUSH_ON = 'lff-games-push';
const KEYED = { apikey: CONFIG.supabaseAnonKey, Authorization: 'Bearer ' + CONFIG.supabaseAnonKey };
const APPLE = /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
const homeScreen = () => navigator.standalone === true || matchMedia('(display-mode: standalone)').matches;
// none: this browser cannot; install: an iPhone that has to open the page from the Home Screen first;
// denied: turned off in the phone's settings; on, off.
function pushState() {
  if (!PUSH_FN) return 'none';
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return APPLE && !homeScreen() ? 'install' : 'none';
  if (Notification.permission === 'denied') return 'denied';
  return Notification.permission === 'granted' && store.get(PUSH_ON, false) ? 'on' : 'off';
}
const keyBytes = (text) => Uint8Array.from(atob(text.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
async function pushOn() {
  // The phone's own question comes first: it is only allowed straight off a tap.
  if (await Notification.requestPermission() !== 'granted') throw new Error('Notifications are turned off for this page in the phone’s settings.');
  const reg = await navigator.serviceWorker.register('/games/sw.js', { scope: '/games/' });
  await navigator.serviceWorker.ready;
  const reply = await fetch(PUSH_FN, { headers: KEYED }).then((r) => r.json()).catch(() => null);
  if (!reply || !reply.key) throw new Error('Notifications are not set up in the game room yet.');
  let sub = await reg.pushManager.getSubscription();
  const held = sub && sub.options && sub.options.applicationServerKey && btoa(String.fromCharCode(...new Uint8Array(sub.options.applicationServerKey)));
  if (sub && held && held !== btoa(String.fromCharCode(...keyBytes(reply.key)))) { await sub.unsubscribe(); sub = null; }
  sub = sub || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(reply.key) });
  await call('room_push_on', { p_sub: sub.toJSON() });
  store.set(PUSH_ON, true);
}
async function pushOff() {
  store.set(PUSH_ON, false);
  const reg = await navigator.serviceWorker.getRegistration('/games/'), sub = reg && await reg.pushManager.getSubscription();
  if (sub) { await call('room_push_off', { p_endpoint: sub.endpoint }).catch(() => {}); await sub.unsubscribe().catch(() => {}); }
}
// On every visit, the room is told again where this device is: the address can change, and so can who is logged in.
async function pushSync() {
  if (pushState() !== 'on') return;
  try {
    const reg = await navigator.serviceWorker.getRegistration('/games/'), sub = reg && await reg.pushManager.getSubscription();
    if (sub) await call('room_push_on', { p_sub: sub.toJSON() }); else store.set(PUSH_ON, false);
  } catch (e) { /* the next visit tries again */ }
}
// Tells the other players at a table. kind is turn, say or ring. Answers how many devices were reached.
async function notify(code, kind, text) {
  if (!PUSH_FN) return 0;
  try {
    const r = await fetch(PUSH_FN, { method: 'POST', headers: { ...KEYED, 'Content-Type': 'application/json' }, body: JSON.stringify({ code, token: await me(), kind, text: text || null }) });
    return (await r.json()).sent || 0;
  } catch (e) { return 0; }
}
function pushDialog(done) {
  const state = pushState(), close = () => { d.close(); if (done) done(); };
  const act = (label, fn) => h('button', { class: 'go', on: { click: async (ev) => {
    ev.currentTarget.disabled = true;
    try { await fn(); close(); toast(pushState() === 'on' ? 'Notifications are on for this device.' : 'Notifications are off for this device.'); }
    catch (e) { toast(e.message || 'That did not work just now.'); ev.target.disabled = false; }
  } } }, label);
  const why = {
    on: 'This device gets a notification when it is your turn and you have stepped away, when the other player says something, and when they ring you.',
    off: 'Get a notification on this device when it is your turn and you have stepped away, when the other player says something, and when they ring you.',
    install: 'On an iPhone or iPad, notifications only work from the Home Screen. Tap Share, then Add to Home Screen, open game/room from the new icon, and turn notifications on there.',
    denied: 'Notifications are turned off for this page in the phone’s or browser’s settings. Turn them on there, then come back here.',
    none: DEV ? 'Notifications are not sent from a local copy.' : 'This browser cannot show notifications from a web page.'
  }[state];
  const d = dialog('Notifications', h('h3', {}, 'Notifications'), h('p', { class: 'why' }, why),
    h('div', { class: 'btns' }, h('button', { class: 'ghost', on: { click: () => d.close() } }, state === 'on' || state === 'off' ? 'Not now' : 'Close'),
      state === 'off' ? act('Turn on', pushOn) : state === 'on' ? act('Turn off', pushOff) : null));
}

ready.then(pushSync).catch(() => {});

// The leaderboard: players with accounts, by games won against each other.
async function showLeaderboard(box, game) {
  let rows;
  try { rows = await rpc('room_leaderboard', { p_game: game || null, p_token: key }); }
  catch (e) { box.replaceChildren(h('p', { class: 'none' }, 'The leaderboard opens once the game room is updated.')); return; }
  if (!rows.length) { box.replaceChildren(h('p', { class: 'none' }, 'Nobody is on it yet. A finished game between two players with accounts puts them here.')); return; }
  box.replaceChildren(h('div', { class: 'tables' }, rows.map((r, i) =>
    h('div', { class: 'trow lb' + (r.me ? ' me' : '') }, h('span', { class: 'rank' }, String(i + 1)), avatarEl(r),
      h('div', { class: 't' }, h('b', {}, r.name), h('span', {}, r.handle)),
      h('span', { class: 'wl' }, h('b', {}, String(r.wins)), ' won · ', String(r.losses), ' lost')))));
}

/* ---------- lists of tables ---------- */
const mine = () => (key ? call('room_mine') : Promise.resolve([]));
const lobby = () => rpc('room_lobby', { p_token: key });
// One line in a list: a table you're at ('mine') or one you could sit down at ('open').
function tableRow(t, kind) {
  const g = GAMES[t.game] || { name: t.game, path: '/games/', options: () => '', score: () => '', idle: () => 'THEIR TURN' };
  const who = kind === 'open' ? t.host : t.players.find((p, i) => i !== t.seat) || null;
  const title = kind === 'open' ? who.name : who ? 'vs ' + who.name : 'Waiting for someone';
  const sub = [g.name, g.options(t.options), kind === 'mine' && g.score(t)].filter(Boolean).join(' · ');
  const badge = kind === 'open' ? (t.mine ? ['YOURS', ''] : ['SIT DOWN', ' sit'])
    : t.status === 'waiting' ? ['OPEN', ''] : t.your_turn ? ['YOUR TURN', ' you'] : t.status === 'over' ? ['GAME OVER', ''] : [g.idle(t), ''];
  return h('a', { class: 'trow', href: `${g.path}?t=${t.code}` }, avatarEl(who), h('div', { class: 't' }, h('b', {}, title), h('span', {}, sub)),
    h('span', { class: 'badge' + badge[1] }, badge[0]));
}
function showTables(box, tables, kind, none) {
  box.replaceChildren(tables.length ? h('div', { class: 'tables' }, tables.map((t) => tableRow(t, kind))) : h('p', { class: 'none' }, none));
}

/* ---------- live nudges: the other page hears about a move the moment it lands ---------- */
// Returns { send(event, payload) }. Every page still polls, so if this never connects the game carries on.
function live(name, handlers, status) {
  const out = { channel: null, send(event, payload) { if (out.channel) out.channel.send({ type: 'broadcast', event, payload: payload || {} }).catch(() => {}); } };
  if (DEV) return out;
  const s = h('script', { src: SUPABASE_JS, integrity: SUPABASE_SRI, crossorigin: 'anonymous' });
  s.onload = () => {
    try {
      const sb = window.supabase.createClient(CONFIG.supabaseUrl, CONFIG.supabaseAnonKey, { auth: { persistSession: false } });
      let ch = sb.channel(name, { config: { broadcast: { self: false } } });
      for (const [event, fn] of Object.entries(handlers)) ch = ch.on('broadcast', { event }, (m) => fn(m.payload || {}));
      ch.subscribe((state) => { out.channel = state === 'SUBSCRIBED' ? ch : null; if (status) status(state === 'SUBSCRIBED'); });
    } catch (e) { out.channel = null; }
  };
  document.head.append(s);
  return out;
}

/* ---------- sound: a few synthesized blips, no files ---------- */
const sound = (() => {
  let ctx = null, on = store.get('lff-games-sound', true);
  function ac() {
    if (!on || !(navigator.userActivation && navigator.userActivation.hasBeenActive)) return null;
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === 'suspended') ctx.resume();
      return ctx;
    } catch (e) { return null; }
  }
  function tone(freq, at, dur, type, vol) {
    const c = ac(); if (!c) return;
    const o = c.createOscillator(), g = c.createGain(), t = c.currentTime + at;
    o.type = type || 'sine'; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(vol || 0.12, t + 0.012); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(c.destination); o.start(t); o.stop(t + dur + 0.03);
  }
  function hiss(at, dur, freq, vol) {
    const c = ac(); if (!c) return;
    const n = Math.max(1, Math.floor(c.sampleRate * dur)), buf = c.createBuffer(1, n, c.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const s = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    s.buffer = buf; f.type = 'bandpass'; f.frequency.value = freq; f.Q.value = 0.9; g.gain.value = vol || 0.2;
    s.connect(f).connect(g).connect(c.destination); s.start(c.currentTime + at);
  }
  return {
    get on() { return on; },
    set(v) { on = !!v; store.set('lff-games-sound', on); },
    draw() { hiss(0, 0.1, 3000, 0.16); },
    place() { hiss(0, 0.07, 1500, 0.24); tone(130, 0, 0.07, 'sine', 0.1); },
    deal() { for (let i = 0; i < 6; i++) hiss(i * 0.07, 0.06, 2600, 0.12); },
    turn() { tone(660, 0, 0.14, 'sine', 0.09); tone(880, 0.1, 0.22, 'sine', 0.09); },
    knock() { for (const at of [0, 0.17]) { tone(165, at, 0.1, 'triangle', 0.34); hiss(at, 0.04, 480, 0.3); } },
    win() { [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.11, 0.34, 'triangle', 0.13)); },
    lose() { [392, 330, 262].forEach((f, i) => tone(f, i * 0.17, 0.36, 'sine', 0.09)); },
    pop() { tone(540, 0, 0.09, 'sine', 0.08); }
  };
})();

return { DEV, GAMES, $, h, store, toast, plural, rpc, call, me, ready, named, profile, saveProfile, key: () => key,
         avatarEl, setAvatar, profileEditor, profileDialog, deviceDialog, dialog, qr, mine, lobby, showTables, live, sound,
         handle: () => handle, accountBox, accountDialog, showLeaderboard, pushState, pushDialog, notify };
})();
