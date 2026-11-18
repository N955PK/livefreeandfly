// ski/lease calendar feed. A phone calendar subscribes to
//   https://<project>.supabase.co/functions/v1/calendar?token=<member's calendar token>
// and gets that member's nights at the house, one event per run of consecutive nights, with who else is there.
// Deploy with JWT verification off (calendar apps can't sign in); the token is the only key.
import { createClient } from 'npm:@supabase/supabase-js@2.45.4';

const db = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!, {
  auth: { persistSession: false },
});
const CORS = { 'Access-Control-Allow-Origin': '*' };
const TOKEN_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Stay = { member_id: string; night: string; guests: number; host_away: boolean; guest_names: string[] | null; note: string | null };
type Member = { id: string; name: string; active: boolean };

const reply = (body: string, status: number, type = 'text/plain; charset=utf-8') =>
  new Response(body, { status, headers: { ...CORS, 'Content-Type': type, 'Cache-Control': 'private, max-age=900' } });

// RFC 5545 text escaping and 75-octet line folding.
const text = (s: string) => s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
function fold(line: string): string {
  const bytes = new TextEncoder().encode(line);
  if (bytes.length <= 75) return line;
  const out: string[] = []; let cur = '', size = 0;
  for (const ch of line) {
    const n = new TextEncoder().encode(ch).length;
    if (size + n > (out.length ? 74 : 75)) { out.push(cur); cur = ''; size = 0; }
    cur += ch; size += n;
  }
  out.push(cur);
  return out.join('\r\n ');
}
const ymd = (k: string) => k.replace(/-/g, '');
const addDay = (k: string, n: number) => { const d = new Date(k + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const nice = (k: string) => new Date(k + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
const first = (m: Member | undefined) => (m?.name || '?').trim().split(/\s+/)[0];

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { headers: { ...CORS, 'Access-Control-Allow-Methods': 'GET' } });
  const token = new URL(req.url).searchParams.get('token') || '';
  if (!TOKEN_RE.test(token)) return reply('Missing or malformed token', 400);

  const { data: tok } = await db.from('calendar_tokens').select('member_id').eq('token', token).maybeSingle();
  if (!tok) return reply('Unknown calendar link', 404);
  const [{ data: members }, { data: stays }, { data: house }] = await Promise.all([
    db.from('members').select('id,name,active'),
    db.from('stays').select('member_id,night,guests,host_away,guest_names,note'),
    db.from('house').select('name,address').eq('id', 1).maybeSingle(),
  ]);
  const byId = new Map((members as Member[] || []).map((m) => [m.id, m]));
  const me = byId.get(tok.member_id);
  if (!me || !me.active) return reply('Unknown calendar link', 404);

  const all = (stays as Stay[] || []).filter((s) => byId.has(s.member_id));
  const mine = all.filter((s) => s.member_id === me.id).sort((a, b) => a.night.localeCompare(b.night));
  const houseName = house?.name || 'Ski house';

  // Who's there on a night, as one line.
  const nightLine = (night: string) => {
    const on = all.filter((s) => s.night === night);
    const people = on.filter((s) => !s.host_away).map((s) => (s.member_id === me.id ? 'You' : first(byId.get(s.member_id))));
    const guests = on.reduce((n, s) => n + (s.guests || 0), 0);
    const count = people.length + guests;
    const mineStay = on.find((s) => s.member_id === me.id);
    const myGuests = mineStay?.guest_names?.length ? ` · your guests: ${mineStay.guest_names.join(', ')}` : '';
    const note = mineStay?.note ? ` · ${mineStay.note}` : '';
    return `${nice(night)}: ${count} ${count === 1 ? 'person' : 'people'} (${people.join(', ') || 'no members'}${guests ? `, +${guests} guest${guests === 1 ? '' : 's'}` : ''})${myGuests}${note}`;
  };

  // Group consecutive nights into one event.
  const runs: Stay[][] = [];
  for (const s of mine) {
    const last = runs[runs.length - 1];
    if (last && addDay(last[last.length - 1].night, 1) === s.night) last.push(s); else runs.push([s]);
  }

  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+/, '');
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//livefreeandfly//ski-lease//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
    `X-WR-CALNAME:${text(houseName)}`, 'REFRESH-INTERVAL;VALUE=DURATION:PT3H', 'X-PUBLISHED-TTL:PT3H',
  ];
  for (const run of runs) {
    const start = run[0].night, end = addDay(run[run.length - 1].night, 1);
    const away = run.every((s) => s.host_away);
    const nights = run.length;
    lines.push(
      'BEGIN:VEVENT',
      `UID:${me.id}-${start}@ski-lease`,
      `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${ymd(start)}`,
      `DTEND;VALUE=DATE:${ymd(end)}`,
      `SUMMARY:${text(away ? `Your guests at ${houseName}` : `${houseName} (${nights} night${nights === 1 ? '' : 's'})`)}`,
      `DESCRIPTION:${text(run.map((s) => nightLine(s.night)).join('\n') + '\n\nCheck out the morning of ' + nice(end) + '.')}`,
      ...(house?.address ? [`LOCATION:${text(house.address)}`] : []),
      'TRANSP:TRANSPARENT',
      'END:VEVENT',
    );
  }
  lines.push('END:VCALENDAR');
  return reply(lines.map(fold).join('\r\n') + '\r\n', 200, 'text/calendar; charset=utf-8');
});
