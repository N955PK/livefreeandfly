// Flight files: the capture-kit record stream — `<dH` (little-endian unix seconds, payload length) then the
// payload, repeated. The bridge writes them to sessions/, the iOS shell to Documents/Flights/, and
// onflight/records.py reads the same bytes in Python.
//
// Most records are 67-byte INS frames (payload[0] === 0x02). A flight can also carry a box record: payload
// [0xB0, ...UTF-8 JSON of the aerobatic box]. The INS decoder skips it, so the box travels inside the .bin
// and a reopened flight comes back with the box it was flown against.
import { decodeIns, INS_SIZE, INS_MSG_ID } from './onflight.js';
import { sampleFromFrame } from './frames.js';

const HEADER = 10;
export const BOX_MARKER = 0xb0;

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

/// The aerobatic box embedded in the flight, or null.
export function boxFromRecords(records) {
  for (const { payload } of records) {
    if (payload.length > 1 && payload[0] === BOX_MARKER) {
      try { return JSON.parse(new TextDecoder().decode(payload.subarray(1))); } catch (e) { return null; }
    }
  }
  return null;
}

/// One box record as bytes ready to write into a .bin (10-byte header + marker + JSON).
export function boxRecordBytes(box) {
  const json = new TextEncoder().encode(JSON.stringify(box));
  const rec = new Uint8Array(HEADER + 1 + json.length);
  const dv = new DataView(rec.buffer);
  dv.setFloat64(0, 0, true);
  dv.setUint16(8, 1 + json.length, true);
  rec[HEADER] = BOX_MARKER;
  rec.set(json, HEADER + 1);
  return rec;
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
  const records = parseRecords(await res.arrayBuffer());
  return { samples: samplesFromRecords(records), box: boxFromRecords(records) };
}
