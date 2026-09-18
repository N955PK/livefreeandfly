// Aerobatic box anchored geodetically: a corner (lat/lon), the true heading of its front edge, and edge
// lengths. Set from the aircraft in flight ("I'm over the corner, flying along the judge line") and
// persisted in localStorage so it survives app restarts and session origins.
import * as THREE from 'three';
import { nedFromLla, worldFromNed, offsetLatLon, FT_TO_M } from './frames.js';
import { getItem, setItem } from './storage.js';

const STORAGE_KEY = 'acroReplay.box';
export const DEFAULT_BOX = { widthM: 3300 * FT_TO_M, depthM: 3300 * FT_TO_M, floorFt: 1500, ceilFt: 3500, judgeSide: 'right', judgeSetbackM: 500 * FT_TO_M, judgeAltFt: 6 };
const DEG = Math.PI / 180;

export function loadBox() {
  try {
    const b = JSON.parse(getItem(STORAGE_KEY));
    return b && Number.isFinite(b.lat) ? { ...DEFAULT_BOX, ...b } : null;
  } catch (e) { return null; }
}

export function saveBox(box) {
  setItem(STORAGE_KEY, box ? JSON.stringify(box) : null);
}

// Box from the judges' position: they stand `judgeSetbackM` outside the front edge at mid-width, facing
// `facingDeg` (true) into the box. A pilot flying the front edge with the judges on the right heads facingDeg + 90.
export function boxFromJudges({ lat, lon, facingDeg, ...dims }) {
  const b = { ...DEFAULT_BOX, ...dims, judgeSide: 'right' };
  const h = (facingDeg + 90) % 360;
  const mid = offsetLatLon(lat, lon, b.judgeSetbackM * Math.cos(facingDeg * DEG), b.judgeSetbackM * Math.sin(facingDeg * DEG));
  const [cLat, cLon] = offsetLatLon(mid[0], mid[1], -(b.widthM / 2) * Math.cos(h * DEG), -(b.widthM / 2) * Math.sin(h * DEG));
  return { ...b, lat: cLat, lon: cLon, headingDeg: h, anchor: 'judges', judges: { lat, lon, facingDeg } };
}

// Box from the aircraft entering it: the aircraft is over the middle of the entry edge, flying into the box
// along its main axis (ground track). The box extends ahead by `widthM` and ±depthM/2 to either side; the
// judges sit on `judgeSide` outside the box, so the front edge (and our corner) is depthM/2 toward them.
export function boxFromEntry({ lat, lon, trackDeg, ...dims }) {
  const b = { ...DEFAULT_BOX, ...dims };
  const h = ((trackDeg % 360) + 360) % 360;
  const towardJudges = (h + (b.judgeSide === 'left' ? -90 : 90)) * DEG;
  const [cLat, cLon] = offsetLatLon(lat, lon, (b.depthM / 2) * Math.cos(towardJudges), (b.depthM / 2) * Math.sin(towardJudges));
  return { ...b, lat: cLat, lon: cLon, headingDeg: h, anchor: 'entry', entry: { lat, lon, trackDeg } };
}

// Where the judges stand for a given box (inverse of the above), for display.
export function judgeLatLon(box) {
  const h = box.headingDeg * DEG;
  const side = box.judgeSide === 'left' ? 1 : -1;
  const toJudges = h - side * Math.PI / 2;
  const mid = offsetLatLon(box.lat, box.lon, (box.widthM / 2) * Math.cos(h), (box.widthM / 2) * Math.sin(h));
  return offsetLatLon(mid[0], mid[1], box.judgeSetbackM * Math.cos(toJudges), box.judgeSetbackM * Math.sin(toJudges));
}

// Judges as an orange camera on the ground, lens toward the box, with a field-of-view wedge that shows the
// facing direction from altitude. Built looking along +z; rotated to face the box.
function judgesCamera() {
  const g = new THREE.Group();
  const orange = new THREE.MeshStandardMaterial({ color: 0xff8c1a, roughness: 0.6 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.4 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(24, 14, 16), orange); body.position.set(0, 7, 0); g.add(body);
  const finder = new THREE.Mesh(new THREE.BoxGeometry(9, 5, 9), orange); finder.position.set(-6, 16.5, -2); g.add(finder);
  const lens = new THREE.Mesh(new THREE.CylinderGeometry(6, 7, 12, 24), dark); lens.rotation.x = Math.PI / 2; lens.position.set(0, 8, 13); g.add(lens);
  const glass = new THREE.Mesh(new THREE.CircleGeometry(4.5, 24), new THREE.MeshStandardMaterial({ color: 0x66aaff, roughness: 0.1 }));
  glass.position.set(0, 8, 19.2); g.add(glass);
  const wedge = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([0, 0.6, 16, -70, 0.6, 260, 70, 0.6, 260], 3));
  g.add(new THREE.Mesh(wedge, new THREE.MeshBasicMaterial({ color: 0xff8c1a, transparent: true, opacity: 0.32, side: THREE.DoubleSide, depthWrite: false })));
  const rays = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([0, 0.7, 16, -70, 0.7, 260, 0, 0.7, 16, 70, 0.7, 260], 3));
  g.add(new THREE.LineSegments(rays, new THREE.LineBasicMaterial({ color: 0xff8c1a, transparent: true, opacity: 0.85 })));
  return g;
}

// Local frame of the group: +x along the front edge (heading), +z to the pilot's right, y up from the ground.
// The box extends away from the judges; judges stand outside the front edge at mid-width.
export function buildBoxGroup(box, origin) {
  const g = new THREE.Group();
  const [e, , s] = worldFromNed(...nedFromLla(box.lat, box.lon, origin[2], origin));
  g.position.set(e, 0, s);
  g.rotation.y = Math.PI / 2 - THREE.MathUtils.degToRad(box.headingDeg);
  const w = box.widthM, d = box.depthM;
  const side = box.judgeSide === 'left' ? 1 : -1;
  const z0 = 0, z1 = side * d;
  const f = box.floorFt * FT_TO_M, c = box.ceilFt * FT_TO_M;
  const rect = (y) => [[0, y, z0], [w, y, z0], [w, y, z1], [0, y, z1]];
  const lines = [];
  const addRect = (pts) => { for (let i = 0; i < 4; i += 1) lines.push(...pts[i], ...pts[(i + 1) % 4]); };
  addRect(rect(0.5)); addRect(rect(f)); addRect(rect(c));
  for (const [x, z] of [[0, z0], [w, z0], [w, z1], [0, z1]]) lines.push(x, 0.5, z, x, c, z);
  const geo = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(lines, 3));
  g.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 })));
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(w, d),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(w / 2, f, (z0 + z1) / 2);
  g.add(floor);
  // Judges: orange camera at the judging position, looking into the box.
  const jz = -side * (box.judgeSetbackM || DEFAULT_BOX.judgeSetbackM);
  // Judge eye altitude above the field. Default is roughly standing height; raise it to keep a realistic angle to
  // the box floor when practising high (e.g. set it a competition floor-height below a lifted floor).
  const ja = (box.judgeAltFt != null ? box.judgeAltFt : DEFAULT_BOX.judgeAltFt) * FT_TO_M;
  const cam = judgesCamera();
  cam.position.set(w / 2, Math.max(0, ja - 1.7), jz);
  cam.rotation.y = side > 0 ? 0 : Math.PI;
  g.add(cam);
  g.userData.judgeMarker = cam;
  g.userData.judgeLocal = new THREE.Vector3(w / 2, ja, jz);
  g.userData.bounds = { w, zMin: Math.min(z0, z1), zMax: Math.max(z0, z1), f, c };
  g.userData.judgeSide = box.judgeSide;
  g.userData.headingDeg = box.headingDeg;
  return g;
}

export function judgeWorldPosition(group, target) {
  return group.localToWorld(target.copy(group.userData.judgeLocal));
}

const tmp = new THREE.Vector3();
export function boxStatus(group, worldPos) {
  const l = group.worldToLocal(tmp.copy(worldPos));
  const b = group.userData.bounds;
  // Offsets outside the box, in metres: one horizontal (the larger of along/across) and one vertical.
  let horiz = null;
  for (const [m, word] of [[-l.x, 'short'], [l.x - b.w, 'long'], [b.zMin - l.z, 'out'], [l.z - b.zMax, 'out']]) {
    if (m > 0.5 && (!horiz || m > horiz.m)) horiz = { m, word };
  }
  const vert = l.y < b.f ? { m: b.f - l.y, word: 'low' } : l.y > b.c ? { m: l.y - b.c, word: 'high' } : null;
  // Normalised coordinates for the minimaps: along the edge (0..1), across from the far edge to the judges'
  // edge (0..1), and altitude from floor (0) to ceiling (1). Values outside 0..1 are outside the box.
  const towardJudges = group.userData.judgeSide === 'left' ? -1 : 1;
  const depth = b.zMax - b.zMin;
  const across = towardJudges > 0 ? (l.z - b.zMin) / depth : (b.zMax - l.z) / depth;
  return {
    inBox: !horiz && !vert, horiz, vert,
    along: l.x / b.w, across, vertical: (l.y - b.f) / (b.c - b.f), towardJudges,
  };
}
