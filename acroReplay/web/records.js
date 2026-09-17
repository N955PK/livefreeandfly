// Flight files: the capture-kit record stream — `<dH` (little-endian unix seconds, payload length) then the
// payload, repeated. The bridge writes them to sessions/, the iOS shell to Documents/Flights/, and
// onflight/records.py reads the same bytes in Python.
import { decodeIns, INS_SIZE, INS_MSG_ID } from './onflight.js';
import { sampleFromFrame } from './frames.js';

const HEADER = 10;

export function parseRecords(buffer) {
  const dv = new DataView(buffer);
  const out = [];
  let off = 0;
  while (off + HEADER <= dv.byteLength) {
    const wall = dv.getFloat64(off, true);
    const n = dv.getUint16(off + 8, true);
    off += HEADER;
    if (off + n > dv.byteLength) break;
    out.push({ wall, payload: new Uint8Array(buffer, off, n) });
    off += n;
  }
  return out;
}

/// INS frames only, decoded into the same sample shape the live paths produce (position left for the caller,
/// who knows the scene origin). Frames before the INS initialised are kept — they carry the timeline.
export function samplesFromRecords(records) {
  const samples = [];
  for (const { wall, payload } of records) {
    if (payload.length !== INS_SIZE || payload[0] !== INS_MSG_ID) continue;
    const f = decodeIns(payload);
    const s = sampleFromFrame(wall, f, null);
    s.lat = f.lat; s.lon = f.lon;
    samples.push(s);
  }
  return samples;
}

export async function loadFlight(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return samplesFromRecords(parseRecords(await res.arrayBuffer()));
}
