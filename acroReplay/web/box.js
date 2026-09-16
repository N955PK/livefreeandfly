// Aerobatic box anchored geodetically: a corner (lat/lon), the true heading of its front edge, and edge
// lengths. Set from the aircraft in flight ("I'm over the corner, flying along the judge line") and
// persisted in localStorage so it survives app restarts and session origins.
import * as THREE from 'three';
import { nedFromLla, worldFromNed, FT_TO_M } from './frames.js';

const STORAGE_KEY = 'acroReplay.box';
export const DEFAULT_BOX = { widthM: 1000, depthM: 1000, floorFt: 1500, ceilFt: 3500, judgeSide: 'right' };
const JUDGE_SETBACK_M = 150;

export function loadBox() {
  try {
    const b = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return b && Number.isFinite(b.lat) ? { ...DEFAULT_BOX, ...b } : null;
  } catch (e) { return null; }
}

export function saveBox(box) {
  if (box) localStorage.setItem(STORAGE_KEY, JSON.stringify(box)); else localStorage.removeItem(STORAGE_KEY);
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
  const judge = new THREE.Mesh(new THREE.CylinderGeometry(4, 4, 2, 16), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  judge.position.set(w / 2, 1, -side * JUDGE_SETBACK_M);
  g.add(judge);
  g.userData.judgeLocal = new THREE.Vector3(w / 2, 1.7, -side * JUDGE_SETBACK_M);
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
