import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';

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
const sun = new THREE.DirectionalLight(0xffffff, 1.2);
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

function buildAircraft() {
  const g = new THREE.Group();
  const red = new THREE.MeshLambertMaterial({ color: 0xd8262c });
  const white = new THREE.MeshLambertMaterial({ color: 0xf4f4f4 });
  const add = (geo, mat, x, y, z, rz = 0) => { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.rotation.z = rz; g.add(m); };
  add(new THREE.BoxGeometry(6.0, 0.9, 1.0), red, -0.6, 0, 0);
  add(new THREE.ConeGeometry(0.5, 1.4, 12), red, 3.1, 0, 0, -Math.PI / 2);
  add(new THREE.BoxGeometry(1.3, 6.0, 0.12), white, 0.3, 0, 0.2);
  add(new THREE.BoxGeometry(1.3, 6.0, 0.12), white, 0.8, 0, -1.0);
  add(new THREE.BoxGeometry(0.8, 2.4, 0.08), white, -3.1, 0, -0.1);
  add(new THREE.BoxGeometry(0.9, 0.08, 1.1), red, -3.1, 0, -0.65);
  return g;
}
const aircraft = buildAircraft();
scene.add(aircraft);

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
const camOffset = new THREE.Vector3(12, 6, 18);
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
    camera.position.set(p.x - 28 * Math.sin(hdg), p.y + 7, p.z + 28 * Math.cos(hdg));
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
connect();

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
