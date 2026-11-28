// game/room's notification sender: a Supabase Edge Function named "push". Paste this whole file into
// Supabase > Edge Functions > Deploy a new function > Via Editor, name it push, and turn "Verify JWT" off for it
// (the pages call it with the publishable key; it does its own checking through the card room).
//
//   GET                                   the public half of the signing key, for a page to subscribe with
//   POST {code, token, kind, text?}       tell the other players at a table (kind: turn, say or ring)
//
// It holds no secret of its own to set up. The signing key pair is made here the first time it runs and kept in
// the database where only this function can read it (room.secrets, through public.push_keys). Who gets told and
// what they are told is decided by public.push_job in games/sql/1_room.sql; this file only seals and delivers.
// Web Push by the book: RFC 8291 (the message is sealed for one device), RFC 8292 (signed so the phone's maker
// knows who sent it), written against WebCrypto so nothing is imported.

const env = (name: string) => (globalThis as any).Deno?.env.get(name) ?? "";
const CONTACT = "https://livefreeandfly.org/games/";   // who a push service can reach about these messages
const enc = new TextEncoder();
const b64u = (bytes: any) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = (text: string): any => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const join = (...parts: any[]): any => { const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0)); let at = 0; for (const p of parts) { out.set(p, at); at += p.length; } return out; };
const hmac = async (key: any, data: any): Promise<any> =>
  new Uint8Array(await crypto.subtle.sign("HMAC", await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]), data));

// A new signing pair: {public: the raw point, base64url; private: a JWK}.
export async function newKeys() {
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign"]);
  return { public: b64u(new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey))), private: await crypto.subtle.exportKey("jwk", pair.privateKey) };
}

// The Authorization header that says who is sending, good for twelve hours, for one push service.
export async function vapid(keys: { public: string; private: JsonWebKey }, endpoint: string, now = Date.now()) {
  const key = await crypto.subtle.importKey("jwk", keys.private, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const part = (o: unknown) => b64u(enc.encode(JSON.stringify(o)));
  const unsigned = part({ typ: "JWT", alg: "ES256" }) + "." + part({ aud: new URL(endpoint).origin, exp: Math.floor(now / 1000) + 12 * 3600, sub: CONTACT });
  const sig = new Uint8Array(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc.encode(unsigned)));
  return `vapid t=${unsigned}.${b64u(sig)}, k=${keys.public}`;
}

// Seals a message for one device (content encoding aes128gcm).
export async function seal(text: string, p256dh: string, auth: string) {
  const theirs = unb64u(p256dh), secret = unb64u(auth), salt = crypto.getRandomValues(new Uint8Array(16));
  const mine = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const minePublic = new Uint8Array(await crypto.subtle.exportKey("raw", mine.publicKey));
  const theirKey = await crypto.subtle.importKey("raw", theirs, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: theirKey }, mine.privateKey, 256));
  const one = new Uint8Array([1]);
  const ikm = await hmac(await hmac(secret, shared), join(enc.encode("WebPush: info\0"), theirs, minePublic, one));
  const prk = await hmac(salt, ikm);
  const cek = (await hmac(prk, join(enc.encode("Content-Encoding: aes128gcm\0"), one))).slice(0, 16);
  const nonce = (await hmac(prk, join(enc.encode("Content-Encoding: nonce\0"), one))).slice(0, 12);
  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, join(enc.encode(text), new Uint8Array([2]))));
  return join(salt, new Uint8Array([0, 0, 16, 0]), new Uint8Array([minePublic.length]), minePublic, sealed);
}

// One message to one device. Answers the push service's status: 201 is delivered, 404 and 410 mean the device is gone.
export async function deliver(keys: { public: string; private: JsonWebKey }, sub: { endpoint: string; p256dh: string; auth: string }, message: unknown) {
  const reply = await fetch(sub.endpoint, {
    method: "POST",
    headers: { Authorization: await vapid(keys, sub.endpoint), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", TTL: "3600", Urgency: "high" },
    body: await seal(JSON.stringify(message), sub.p256dh, sub.auth),
  });
  return reply.status;
}

async function room(fn: string, args: unknown) {
  const key = env("SUPABASE_SERVICE_ROLE_KEY");
  const reply = await fetch(`${env("SUPABASE_URL")}/rest/v1/rpc/${fn}`, {
    method: "POST", headers: { "Content-Type": "application/json", apikey: key, Authorization: "Bearer " + key }, body: JSON.stringify(args),
  });
  const body = await reply.json().catch(() => null);
  if (!reply.ok) throw new Error((body && body.message) || `the card room answered ${reply.status}`);
  return body;
}
const keysOnce = async () => (await room("push_keys", {})) || (await room("push_keys", { p_set: await newKeys() }));

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" };
const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

export async function handle(request: Request) {
  if (request.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    const keys = await keysOnce();
    if (request.method === "GET") return answer({ key: keys.public });
    const ask = await request.json();
    const job = await room("push_job", { p_code: String(ask.code || ""), p_token: String(ask.token || ""), p_kind: String(ask.kind || ""), p_text: ask.text == null ? null : String(ask.text) });
    const message = { title: job.title, body: job.body, url: job.url, tag: job.tag };
    const results = await Promise.all((job.subs || []).map(async (sub: any) => {
      const status = await deliver(keys, sub, message).catch(() => 0);
      if (status === 404 || status === 410) await room("push_gone", { p_endpoint: sub.endpoint }).catch(() => null);
      return status;
    }));
    return answer({ sent: results.filter((s) => s >= 200 && s < 300).length });
  } catch (error) {
    return answer({ error: String((error as Error).message || error) }, 400);
  }
}

if ((globalThis as any).Deno) (globalThis as any).Deno.serve(handle);
