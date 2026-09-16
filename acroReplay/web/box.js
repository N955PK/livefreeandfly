// Aerobatic box anchored geodetically: a corner (lat/lon), the true heading of its front edge, and edge
// lengths. Set from the aircraft in flight ("I'm over the corner, flying along the judge line") and
// persisted in localStorage so it survives app restarts and session origins.
import * as THREE from 'three';
import { nedFromLla, worldFromNed, offsetLatLon, FT_TO_M } from './frames.js';
import { getItem, setItem } from './storage.js';

const STORAGE_KEY = 'acroReplay.box';
export const DEFAULT_BOX = { widthM: 1000, depthM: 1000, floorFt: 1500, ceilFt: 3500, judgeSide: 'right', judgeSetbackM: 150 };
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
  return { ...b, lat: cLat, lon: cLon, headingDeg: h };
}

// Where the judges stand for a given box (inverse of the above), for display.
export function judgeLatLon(box) {
  const h = box.headingDeg * DEG;
  const side = box.judgeSide === 'left' ? 1 : -1;
  const toJudges = h - side * Math.PI / 2;
  const mid = offsetLatLon(box.lat, box.lon, (box.widthM / 2) * Math.cos(h), (box.widthM / 2) * Math.sin(h));
  return offsetLatLon(mid[0], mid[1], box.judgeSetbackM * Math.cos(toJudges), box.judgeSetbackM * Math.sin(toJudges));
}

function labelSprite(text) {
  const c = document.createElement('canvas'); c.width = 512; c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = 'rgba(0,0,0,0.55)'; g.beginPath(); g.roundRect(8, 8, 496, 112, 24); g.fill();
  g.fillStyle = '#fff'; g.font = 'bold 76px -apple-system, system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(text, 256, 66);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
  sprite.scale.set(60, 15, 1);
  return sprite;
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
  // Judges: a disc on the ground, a striped pole, and a label readable from altitude.
  const jz = -side * (box.judgeSetbackM || DEFAULT_BOX.judgeSetbackM);
  const disc = new THREE.Mesh(new THREE.CircleGeometry(8, 32),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.6, depthWrite: false }));
  disc.rotation.x = -Math.PI / 2; disc.position.set(w / 2, 0.6, jz); g.add(disc);
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 12, 12), new THREE.MeshBasicMaterial({ color: 0xff3b30 }));
  pole.position.set(w / 2, 6, jz); g.add(pole);
  const label = labelSprite('JUDGES'); label.position.set(w / 2, 22, jz); g.add(label);
  const sight = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(w / 2, 0.6, jz), new THREE.Vector3(w / 2, 0.6, 0)]),
    new THREE.LineDashedMaterial({ color: 0xffffff, dashSize: 6, gapSize: 6, transparent: true, opacity: 0.7 }));
  sight.computeLineDistances(); g.add(sight);
  g.userData.judgeLocal = new THREE.Vector3(w / 2, 1.7, jz);
  g.userData.bounds = { w, zMin: Math.min(z0, z1), zMax: Math.max(z0, z1), f, c };
  return g;
}

export function judgeWorldPosition(group, target) {
  return group.localToWorld(target.copy(group.userData.judgeLocal));
}

const tmp = new THREE.Vector3();
export function boxStatus(group, worldPos) {
  const l = group.worldToLocal(tmp.copy(worldPos));
  const b = group.userData.bounds;
  const out = [];
  const add = (v, unit, word) => { const n = Math.round(v); if (n > 0) out.push(`${n} ${unit} ${word}`); };
  add(-l.x, 'm', 'short');
  add(l.x - b.w, 'm', 'long');
  add(b.zMin - l.z, 'm', 'out');
  add(l.z - b.zMax, 'm', 'out');
  add((b.f - l.y) / FT_TO_M, 'ft', 'low');
  add((l.y - b.c) / FT_TO_M, 'ft', 'high');
  return { inBox: out.length === 0, text: out.length ? out.join(' · ') : 'IN BOX' };
}
