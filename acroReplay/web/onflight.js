// Decoder for the OnFlight Hub's 67-byte UDP INS frame (docs/PROTOCOL.md). Mirrors onflight/udp_ins.py.
export const INS_SIZE = 67;
export const INS_MSG_ID = 0x02;

export function base64ToBytes(b64) {
  const s = atob(b64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i += 1) out[i] = s.charCodeAt(i);
  return out;
}

export function decodeIns(bytes) {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (dv.byteLength !== INS_SIZE) throw new Error(`expected ${INS_SIZE}-byte INS frame, got ${dv.byteLength}`);
  if (dv.getUint8(0) !== INS_MSG_ID) throw new Error(`unexpected message id ${dv.getUint8(0)}`);
  const flags0 = dv.getUint8(1);
  const gnss = dv.getUint8(10);
  return {
    init: (flags0 & 0x08) !== 0,
    ok: (flags0 & 0x10) !== 0,
    gnssOk: (flags0 & 0x80) !== 0,
    fix: gnss & 0x07,
    sats: gnss >> 3,
    hacc: dv.getUint8(7) / 10,
    vacc: dv.getUint8(8) / 10,
    utc: Date.UTC(1970 + dv.getUint8(11), dv.getUint8(12) - 1, dv.getUint8(13), dv.getUint8(14), dv.getUint8(15), dv.getUint8(16)),
    pitch: dv.getInt16(17, true) / 100,
    roll: dv.getInt16(19, true) / 100,
    decl: dv.getInt16(21, true) / 100,
    hdg: dv.getUint16(23, true) / 100,
    gs: dv.getUint16(25, true) / 100,
    trk: dv.getUint16(27, true) / 100,
    fpa: dv.getInt16(29, true) / 100,
    vs: dv.getInt16(31, true) / 10,
    nz: dv.getInt16(33, true) / 1000,
    rates: [dv.getInt16(37, true) / 10, dv.getInt16(35, true) / 10, dv.getInt16(39, true) / 10],
    accel: [dv.getInt16(41, true) / 1000, dv.getInt16(43, true) / 1000, dv.getInt16(45, true) / 1000],
    altWgs84: dv.getUint16(47, true) - 10000,
    alt: dv.getUint16(49, true) - 10000,
    cabinAlt: dv.getUint16(51, true) - 10000,
    staticPa: dv.getUint16(53, true) * 2,
    lat: dv.getInt32(55, true) / 1e7,
    lon: dv.getInt32(59, true) / 1e7,
    t: dv.getUint32(63, true) / 1000,
  };
}
