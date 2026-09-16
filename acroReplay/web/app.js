import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { OBJLoader } from 'three/addons/OBJLoader.js';
import { MTLLoader } from 'three/addons/MTLLoader.js';
import { decodeIns, base64ToBytes } from './onflight.js';
import { Origin, sampleFromFrame } from './frames.js';

const BOX_M = 1000;
const JUDGE_DISTANCE_M = 700;
const TRAIL_MAX = 50 * 90;
const RENDER_DELAY_MS = 80;
const STALE_MS = 400;

const canvas = document.getElementById('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9ec9ee);
scene.fog = new THREE.Fog(0x9ec9ee, 2000, 8000);
const camera = new THREE.PerspectiveCamera(55, 1, 0.5, 20000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.enablePan = false;

scene.add(new THREE.HemisphereLight(0xffffff, 0x4d6b3a, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(300, 800, 200);
scene.add(sun);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(8000, 8000), new THREE.MeshLambertMaterial({ color: 0x6f9a5c }));
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.05;
scene.add(ground);
scene.add(new THREE.GridHelper(3000, 30, 0x86a878, 0x86a878));

function buildBox() {
  const h = BOX_M / 2;
  const c = [[-h, 0, -h], [h, 0, -h], [h, 0, h], [-h, 0, h], [-h, BOX_M, -h], [h, BOX_M, -h], [h, BOX_M, h], [-h, BOX_M, h]];
  const edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
  const pts = edges.flatMap(([a, b]) => [...c[a], ...c[b]]);
  const geo = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  const box = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.75 }));
  const judge = new THREE.Mesh(new THREE.CylinderGeometry(3, 3, 1.5, 16), new THREE.MeshLambertMaterial({ color: 0xffffff }));
  judge.position.set(0, 0.75, JUDGE_DISTANCE_M);
  scene.add(box, judge);
}
buildBox();

function sunburstTexture(rays, spread) {
  // Christen Eagle scheme: white base, rainbow "feather" rays fanning back from the nose along +v.
  const c = document.createElement('canvas'); c.width = 512; c.height = 1024;
  const g = c.getContext('2d');
  g.fillStyle = '#f7f7f4'; g.fillRect(0, 0, c.width, c.height);
  const colors = ['#d62828', '#f77f00', '#fcbf49', '#2a9d3f', '#1d6fd6', '#6a3fb5'];
  const n = colors.length * rays;
  for (let i = 0; i < n; i += 1) {
    const x0 = c.width * (0.5 + (i / (n - 1) - 0.5) * spread);
    g.fillStyle = colors[i % colors.length];
    g.beginPath();
    g.moveTo(c.width / 2, 40);
    g.lineTo(x0 - 34, c.height);
    g.lineTo(x0 + 34, c.height);
    g.closePath();
    g.fill();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function buildAircraft() {
  const g = new THREE.Group();
  const paint = new THREE.MeshStandardMaterial({ map: sunburstTexture(2, 1.6), roughness: 0.45, metalness: 0.05 });
  const wingPaint = new THREE.MeshStandardMaterial({ map: sunburstTexture(3, 1.9), roughness: 0.45, metalness: 0.05 });
  const white = new THREE.MeshStandardMaterial({ color: 0xf7f7f4, roughness: 0.5 });
  const black = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.8 });
  const glass = new THREE.MeshStandardMaterial({ color: 0x8fb7d8, transparent: true, opacity: 0.55, roughness: 0.1 });
  const add = (mesh, x, y, z, rx = 0, ry = 0, rz = 0) => { mesh.position.set(x, y, z); mesh.rotation.set(rx, ry, rz); g.add(mesh); return mesh; };

  // Fuselage: lathe profile along its axis (nose at +x). Lathe axis is +y, so rotate onto +x.
  const profile = [[0.02, 2.85], [0.28, 2.75], [0.44, 2.2], [0.5, 1.2], [0.52, 0.3], [0.46, -0.5], [0.34, -1.5], [0.2, -2.4], [0.05, -2.8], [0.0, -2.82]]
    .map(([r, x]) => new THREE.Vector2(r, x));
  add(new THREE.Mesh(new THREE.LatheGeometry(profile, 28), paint), 0, 0, 0, 0, 0, -Math.PI / 2);
  add(new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.35, 24, 1, false, 0, Math.PI), glass), 0.15, 0, -0.45, Math.PI / 2, 0, -Math.PI / 2);

  // Wings: lower at z=+0.35, upper staggered forward at z=-1.05; span 6 m, chord 1.2 m.
  const wingGeo = new THREE.BoxGeometry(1.2, 6.0, 0.11);
  add(new THREE.Mesh(wingGeo, wingPaint), 0.1, 0, 0.35);
  add(new THREE.Mesh(wingGeo, wingPaint), 0.55, 0, -1.05);
  // Interplane I-struts and cabane struts.
  const strut = new THREE.CylinderGeometry(0.03, 0.03, 1.4, 8);
  for (const y of [-2.2, 2.2, -0.5, 0.5]) add(new THREE.Mesh(strut, white), 0.35, y, -0.35, 0, 0, Math.PI / 2 * 0 + (y > -1 && y < 1 ? 0 : 0)).rotation.set(Math.PI / 2, 0, 0);
  for (const y of [-2.2, 2.2]) add(new THREE.Mesh(strut, white), 0.35, y, -0.35).rotation.set(Math.PI / 2, 0, 0);

  // Tail: horizontal stabilizer/elevator, vertical fin/rudder (up is -z).
  add(new THREE.Mesh(new THREE.BoxGeometry(0.75, 2.3, 0.07), wingPaint), -2.45, 0, -0.05);
  add(new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.07, 1.05), paint), -2.45, 0, -0.6);

  // Landing gear with wheel pants, tailwheel, prop and spinner.
  for (const y of [-0.9, 0.9]) {
    add(new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.06, 0.55), white), 1.0, y * 0.75, 0.6, 0, 0, y > 0 ? -0.5 : 0.5);
    add(new THREE.Mesh(new THREE.SphereGeometry(0.28, 16, 12), white), 1.0, y, 0.85).scale.set(1.4, 0.45, 0.9);
    add(new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.12, 16), black), 1.0, y, 0.98, Math.PI / 2, 0, 0);
  }
  add(new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.06, 12), black), -2.6, 0, 0.3, Math.PI / 2, 0, 0);
  add(new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.4, 16), white), 3.05, 0, 0, 0, 0, -Math.PI / 2);
  add(new THREE.Mesh(new THREE.BoxGeometry(0.03, 1.9, 0.14), black), 2.9, 0, 0, 0.6, 0, 0);
  return g;
}
// Licensed Christen Eagle model (web/models/, not in git): cm units, Y up, nose +Z, right wing -X.
// Rotated into the FRD body frame and scaled to metres; the procedural model stands in until it loads.
const aircraft = new THREE.Group();
const placeholder = buildAircraft();
aircraft.add(placeholder);
scene.add(aircraft);
function loadEagleModel() {
  const path = './models/eagle/';
  new MTLLoader().setPath(path).load('eagle.mtl', (mtl) => {
    mtl.preload();
    new OBJLoader().setMaterials(mtl).setPath(path).load('eagle.obj', (obj) => {
      obj.traverse((m) => {
        if (!m.isMesh) return;
        if (/canopy/i.test(m.name)) m.material = new THREE.MeshStandardMaterial({ color: 0x9fc5e8, transparent: true, opacity: 0.35, roughness: 0.1 });
        else m.material.side = THREE.DoubleSide;
      });
      const pivot = new THREE.Group();
      pivot.setRotationFromMatrix(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, -1), new THREE.Vector3(1, 0, 0)));
      pivot.scale.setScalar(0.01);
      obj.position.set(0, -1.6, -30);
      pivot.add(obj);
      aircraft.remove(placeholder);
      aircraft.add(pivot);
    }, undefined, (err) => console.error('eagle model failed', err));
  }, undefined, (err) => console.error('eagle mtl failed', err));
}
loadEagleModel();

const trailPos = new Float32Array(TRAIL_MAX * 3);
const trailGeo = new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
trailGeo.setDrawRange(0, 0);
scene.add(new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: 0xff7a00 })));
let trailLen = 0;
function pushTrail(v) {
  if (trailLen === TRAIL_MAX) { trailPos.copyWithin(0, TRAIL_MAX * 3 / 2); trailLen = TRAIL_MAX / 2; }
  trailPos.set([v.x, v.y, v.z], trailLen * 3);
  trailLen += 1;
  trailGeo.setDrawRange(0, trailLen);
  trailGeo.attributes.position.needsUpdate = true;
}
function clearTrail() { trailLen = 0; trailGeo.setDrawRange(0, 0); }

const samples = [];
let latest = null;
let lastRecv = 0;
let socketOpen = false;
function onSample(s, seedOnly = false) {
  s.recv = performance.now();
  if (s.pos) {
    s.v = new THREE.Vector3(...s.pos);
    s.q = new THREE.Quaternion(...s.quat);
    pushTrail(s.v);
    if (!seedOnly) {
      samples.push(s);
      if (samples.length > 100) samples.splice(0, samples.length - 100);
    }
  }
  latest = s;
  lastRecv = s.recv;
}

const tmpV = new THREE.Vector3();
const tmpQ = new THREE.Quaternion();
function poseAt(t) {
  if (!samples.length) return null;
  const last = samples[samples.length - 1];
  if (t >= last.recv) return last;
  let i = samples.length - 1;
  while (i > 0 && samples[i - 1].recv > t) i -= 1;
  if (i === 0) return samples[0];
  const a = samples[i - 1], b = samples[i];
  const f = (t - a.recv) / Math.max(1, b.recv - a.recv);
  tmpV.lerpVectors(a.v, b.v, f);
  tmpQ.slerpQuaternions(a.q, b.q, f);
  return { v: tmpV, q: tmpQ };
}

let camMode = 'orbit';
const camOffset = new THREE.Vector3(8, 4, 12);
function setCamMode(mode) {
  camMode = mode;
  document.querySelectorAll('#controls [data-cam]').forEach(b => b.classList.toggle('on', b.dataset.cam === mode));
  controls.enabled = mode === 'orbit';
  if (mode === 'orbit') camera.position.copy(aircraft.position).add(camOffset);
}
document.querySelectorAll('#controls [data-cam]').forEach(b => b.addEventListener('click', () => setCamMode(b.dataset.cam)));
document.getElementById('clear').addEventListener('click', clearTrail);

function updateCamera() {
  const p = aircraft.position;
  if (camMode === 'orbit') {
    camera.position.sub(controls.target).add(p);
    controls.target.copy(p);
    controls.update();
  } else if (camMode === 'judge') {
    camera.position.set(0, 1.7, JUDGE_DISTANCE_M);
    camera.lookAt(p);
  } else {
    const hdg = THREE.MathUtils.degToRad(latest ? latest.hdg : 0);
    camera.position.set(p.x - 18 * Math.sin(hdg), p.y + 5, p.z + 18 * Math.cos(hdg));
    camera.lookAt(p);
  }
}

const hud = Object.fromEntries(['hdg', 'pitch', 'roll', 'nz', 'alt', 'gs'].map(id => [id, document.getElementById(id)]));
const status = document.getElementById('status');
function updateHud(now) {
  const s = latest;
  let text, cls;
  if (!socketOpen) { text = 'disconnected'; cls = 'bad'; }
  else if (!s || now - lastRecv > STALE_MS) { text = 'NO DATA'; cls = 'bad'; }
  else if (!s.init) { text = `INS init… fix ${s.fix} · ${s.sats} sats`; cls = ''; }
  else if (!s.ok) { text = `INS degraded · ${s.sats} sats`; cls = ''; }
  else { text = `LIVE · ${s.sats} sats · ±${s.hacc.toFixed(0)} ft`; cls = 'good'; }
  status.textContent = text;
  status.className = `pill ${cls}`;
  if (!s) return;
  hud.hdg.textContent = String(Math.round(s.hdg) % 360).padStart(3, '0');
  hud.pitch.textContent = s.pitch.toFixed(1);
  hud.roll.textContent = s.roll.toFixed(1);
  hud.nz.textContent = s.nz.toFixed(2);
  hud.alt.textContent = Math.round(s.alt);
  hud.gs.textContent = Math.round(s.gs);
}

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { socketOpen = true; };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.history) { clearTrail(); msg.history.forEach(s => onSample(s, true)); return; }
    onSample(msg);
  };
  ws.onclose = () => { socketOpen = false; setTimeout(connect, 1000); };
}
// Inside the iOS shell the native side pushes raw 67-byte frames (base64) instead of a bridge WebSocket.
const nativeHandler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.acro;
if (nativeHandler) {
  const origin = new Origin();
  window.acroReplay = {
    frame(b64, wall) {
      const f = decodeIns(base64ToBytes(b64));
      if (f.init) origin.update(f);
      onSample(sampleFromFrame(wall, f, origin.value));
    },
  };
  socketOpen = true;
  nativeHandler.postMessage('ready');
} else {
  connect();
}

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();
setCamMode('orbit');

function frame() {
  const now = performance.now();
  const pose = poseAt(now - RENDER_DELAY_MS);
  if (pose) { aircraft.position.copy(pose.v); aircraft.quaternion.copy(pose.q); }
  updateCamera();
  updateHud(now);
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
