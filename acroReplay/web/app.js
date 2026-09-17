import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { OBJLoader } from 'three/addons/OBJLoader.js';
import { MTLLoader } from 'three/addons/MTLLoader.js';
import { Line2 } from 'three/addons/Line2.js';
import { LineMaterial } from 'three/addons/LineMaterial.js';
import { LineGeometry } from 'three/addons/LineGeometry.js';
import { decodeIns, base64ToBytes } from './onflight.js';
import { Origin, sampleFromFrame, worldQuaternion, nedFromLla, worldFromNed, FT_TO_M } from './frames.js';
import { buildTileGround, ATTRIBUTION } from './tiles.js';
import { buildHangar, HANGAR } from './hangar.js';
import { DEFAULT_BOX, loadBox, saveBox, buildBoxGroup, judgeWorldPosition, boxStatus, boxFromJudges, boxFromEntry, judgeLatLon } from './box.js';
import { getItem, setItem } from './storage.js';
import { offsetLatLon } from './frames.js';
import * as units from './units.js';

const params = new URLSearchParams(location.search);
const GROUND_M = (parseFloat(params.get('ground_ft')) || 163) * FT_TO_M;
const TILES = params.get('tiles') !== 'none';
const JUDGE_DISTANCE_M = 700;
const RENDER_DELAY_MS = 100;
const STALE_MS = 400;
const TRAIL_HZ = 25;
const TRAIL_SECONDS = 180;
const TRAIL_MAX = TRAIL_HZ * TRAIL_SECONDS;
const REST_AFTER_MS = 3000;   // no frames this long → park the aircraft
const HOME_FIELD = [36.93575, -121.78975];   // KWVI, used only when nothing else says where we are
const HUD_INTERVAL_MS = 50;
const HANGAR_VIEW = new THREE.Vector3(6.5, 2.2, -7);   // orbit camera start relative to the parked aircraft
// Inside the iOS shell the native side pushes raw INS frames and phone GPS fixes instead of a bridge WebSocket.
const nativeHandler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.acro;

const canvas = document.getElementById('view');
const hud = Object.fromEntries(['nz', 'alt', 'alt-u', 'boxstat', 'minis', 'plan-dot', 'plan-hdg', 'vert-dot'].map(id => [id, document.getElementById(id)]));
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
const HORIZON = new THREE.Color(0xcfe0ee);
scene.fog = new THREE.Fog(HORIZON, 15000, 170000);
const camera = new THREE.PerspectiveCamera(55, 1, 1, 250000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.enablePan = false;
controls.minDistance = 4;
controls.maxDistance = 3000;

scene.add(new THREE.HemisphereLight(0xffffff, 0x4d6b3a, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(300, 800, 200);
scene.add(sun);

const sky = new THREE.Mesh(new THREE.SphereGeometry(200000, 32, 16), new THREE.ShaderMaterial({
  side: THREE.BackSide, depthWrite: false, fog: false,
  uniforms: { top: { value: new THREE.Color(0x3d7fd6) }, horizon: { value: HORIZON } },
  vertexShader: 'varying vec3 vPos; void main(){ vPos = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: 'uniform vec3 top; uniform vec3 horizon; varying vec3 vPos; void main(){ float h = clamp(vPos.y / 200000.0, 0.0, 1.0); gl_FragColor = vec4(mix(horizon, top, pow(h, 0.45)), 1.0); }',
}));
sky.renderOrder = -100;
scene.add(sky);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(400000, 400000), new THREE.MeshLambertMaterial({ color: 0x6f9a5c, depthWrite: false }));
ground.rotation.x = -Math.PI / 2;
ground.renderOrder = -20;
scene.add(ground);
const grid = new THREE.GridHelper(4000, 40, 0x86a878, 0x86a878);
grid.position.y = 0.05;
scene.add(grid);
const hangar = buildHangar(scene);
let hangarMode = false;
let tileGround = null;
let originLatLon = null;
let satellite = TILES && getItem('acroReplay.ground') !== 'plain';
function applyGround() {
  if (tileGround && tileGround.visible !== undefined) tileGround.visible = satellite && !hangarMode;
  grid.visible = !satellite && !hangarMode;
  document.getElementById('ground-toggle').textContent = satellite ? 'Sat' : 'Plain';
  document.getElementById('attribution').textContent = satellite && tileGround && !hangarMode ? ATTRIBUTION : '';
}
function ensureGround(lat, lon) {
  if (tileGround || !TILES) return;
  tileGround = true;
  buildTileGround(scene, [lat, lon]).then((g) => { tileGround = g; applyGround(); });
}
function onOriginKnown(lat, lon) {
  if (originLatLon) return;
  originLatLon = [lat, lon, GROUND_M];
  ensureGround(lat, lon);
  rebuildBox();
}
// Without live data the aircraft waits in the hangar; imagery, box and trail belong to the flight view.
// Map picking is the exception: it needs the ground, so it leaves the hangar while active.
function applyScene() {
  const inHangar = parked && camMode !== 'map';
  if (inHangar === hangarMode) return;
  hangarMode = inHangar;
  hangar.visible = inHangar;
  hangar.userData.setLit(inHangar);
  trail.visible = !inHangar;
  showProp(!inHangar);
  if (boxGroup) boxGroup.visible = !inHangar;
  applyGround();
  if (inHangar) {
    hangarControls();
    controls.target.copy(aircraft.position);
    camera.position.copy(aircraft.position).add(HANGAR_VIEW);
    controls.update();
  } else {
    controls.maxDistance = 3000;
    setCamMode(camMode);
  }
}
function hangarControls() {
  controls.enabled = true;
  controls.enableRotate = true;
  controls.enablePan = false;
  controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  controls.touches.ONE = THREE.TOUCH.ROTATE;
  controls.maxDistance = Math.min(HANGAR.width, HANGAR.depth) / 2 - 3;
  controls.maxPolarAngle = Math.PI / 2 - 0.03;
  camera.up.set(0, 1, 0);
  camera.fov = DEFAULT_FOV;
  camera.updateProjectionMatrix();
}
// Phone GPS: where we are when the Hub isn't talking — origin for the imagery, and the judges' "Use my location".
let phoneFix = null;
let judgesWantPhoneFix = false;
function onPhoneFix(lat, lon, acc) {
  phoneFix = { lat, lon, acc, t: performance.now() };
  if (!originLatLon) onOriginKnown(lat, lon);
  if (judgesWantPhoneFix) { judgesWantPhoneFix = false; judgesFromPhone(); }
}
function startPhoneLocation() {   // browser fallback; the iOS shell feeds CoreLocation fixes via acroReplay.location()
  if (nativeHandler || !navigator.geolocation) return;
  navigator.geolocation.watchPosition((p) => onPhoneFix(p.coords.latitude, p.coords.longitude, p.coords.accuracy), () => {},
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
}
function placeParked() {
  aircraft.position.copy(REST.pos);
  aircraft.quaternion.copy(REST.quat);
}
document.getElementById('ground-toggle').addEventListener('click', () => {
  satellite = !satellite;
  setItem('acroReplay.ground', satellite ? 'sat' : 'plain');
  applyGround();
});


// Aerobatic box: set from the aircraft's live position and heading; edges and limits editable in the panel.
let box = loadBox();
let boxGroup = null;
const boxInputs = { widthM: 'box-w', depthM: 'box-d', floorFt: 'box-f', ceilFt: 'box-c', judgeSide: 'box-side', judgeSetbackM: 'j-set' };
const LEN_M = new Set(['widthM', 'depthM', 'judgeSetbackM']);
const LEN_FT = new Set(['floorFt', 'ceilFt']);
function readBoxInputs() {
  const v = {};
  for (const [k, id] of Object.entries(boxInputs)) {
    const el = document.getElementById(id);
    if (el.type !== 'number') { v[k] = el.value; continue; }
    const raw = parseFloat(el.value);
    if (!Number.isFinite(raw)) { v[k] = DEFAULT_BOX[k]; continue; }
    v[k] = LEN_M.has(k) ? units.unitToM(raw) : LEN_FT.has(k) ? units.unitToFt(raw) : raw;
  }
  return v;
}
function writeBoxInputs(b) {
  for (const [k, id] of Object.entries(boxInputs)) {
    const el = document.getElementById(id);
    el.value = LEN_M.has(k) ? Math.round(units.mToUnit(b[k])) : LEN_FT.has(k) ? Math.round(units.ftToUnit(b[k])) : b[k];
  }
}
function applyUnits() {
  document.querySelectorAll('.u-len').forEach((e) => { e.textContent = units.unit; });
  document.querySelectorAll('#units [data-unit]').forEach((btn) => btn.classList.toggle('on', btn.dataset.unit === units.unit));
  hud['alt-u'].textContent = units.unit;
  writeBoxInputs(box || DEFAULT_BOX);
  rebuildBox();
}
document.querySelectorAll('#units [data-unit]').forEach((btn) => btn.addEventListener('click', () => { units.setUnit(btn.dataset.unit); applyUnits(); }));
function rebuildBox() {
  if (boxGroup) { scene.remove(boxGroup); boxGroup = null; }
  if (box && !originLatLon) { onOriginKnown(box.lat, box.lon); return; }
  if (box && originLatLon) {
    boxGroup = buildBoxGroup(box, originLatLon);
    boxGroup.visible = !hangarMode;
    scene.add(boxGroup);
  }
  const info = document.getElementById('box-info');
  if (box) {
    const [jLat, jLon] = judgeLatLon(box);
    const how = box.anchor === 'judges' ? 'set from judges' : box.anchor === 'entry' ? 'set from flight path' : 'saved';
    const u = units.unit, w = Math.round(units.mToUnit(box.widthM)), d = Math.round(units.mToUnit(box.depthM));
    const f = Math.round(units.ftToUnit(box.floorFt)), c = Math.round(units.ftToUnit(box.ceilFt));
    info.textContent = `Box ${how} · ${w}×${d} ${u} · ${f}–${c} ${u} · edge ${Math.round(box.headingDeg)}° · judges at ${jLat.toFixed(5)}, ${jLon.toFixed(5)}`;
  } else {
    info.textContent = 'No box set. Set it from the aircraft in flight, or from the judges\' position on the ground.';
  }
}
document.querySelectorAll('.ptab').forEach((tab) => tab.addEventListener('click', () => {
  document.querySelectorAll('.ptab').forEach((b) => b.classList.toggle('on', b === tab));
  document.getElementById('mode-aircraft').classList.toggle('hidden', tab.dataset.mode !== 'aircraft');
  document.getElementById('mode-judges').classList.toggle('hidden', tab.dataset.mode !== 'judges');
}));
function judgesFromPhone() {
  const msg = document.getElementById('j-msg');
  if (!phoneFix) { judgesWantPhoneFix = true; msg.textContent = 'Waiting for the phone\'s GPS…'; return; }
  document.getElementById('j-lat').value = phoneFix.lat.toFixed(5);
  document.getElementById('j-lon').value = phoneFix.lon.toFixed(5);
  if (!originLatLon) onOriginKnown(phoneFix.lat, phoneFix.lon);
  msg.textContent = `Judges set to your position (±${units.fmtLen(phoneFix.acc)}). Type the direction they face and tap Place box, or tap Pick on map and touch the box centre.`;
}
document.getElementById('j-here').addEventListener('click', () => {
  const msg = document.getElementById('j-msg');
  if (!nativeHandler && !navigator.geolocation) { msg.textContent = 'Location not available here (needs the app or https).'; return; }
  if (!nativeHandler && !phoneFix) {
    navigator.geolocation.getCurrentPosition((p) => onPhoneFix(p.coords.latitude, p.coords.longitude, p.coords.accuracy),
      (err) => { judgesWantPhoneFix = false; msg.textContent = `Location failed: ${err.message}`; }, { enableHighAccuracy: true, timeout: 15000 });
  }
  judgesFromPhone();
});
// Pick the judges on the map: first tap = where they stand, second tap = toward the box centre (sets facing).
const raycaster = new THREE.Raycaster();
const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
function groundLatLon(clientX, clientY) {
  if (!originLatLon) return null;
  raycaster.setFromCamera(new THREE.Vector2((clientX / window.innerWidth) * 2 - 1, -(clientY / window.innerHeight) * 2 + 1), camera);
  const hit = raycaster.ray.intersectPlane(groundPlane, new THREE.Vector3());
  if (!hit) return null;
  return { latLon: offsetLatLon(originLatLon[0], originLatLon[1], -hit.z, hit.x), world: hit };
}
function addPickMarker(world, color) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(6, 16, 12), new THREE.MeshBasicMaterial({ color }));
  m.position.copy(world).setY(6);
  pickMarkers.add(m);
}
let pickDown = null;
canvas.addEventListener('pointerdown', (e) => { pickDown = [e.clientX, e.clientY]; });
canvas.addEventListener('pointerup', (e) => {
  if (!pickState || pickState === 'done' || !pickDown || Math.hypot(e.clientX - pickDown[0], e.clientY - pickDown[1]) > 8) return;
  const g = groundLatLon(e.clientX, e.clientY);
  const msg = document.getElementById('pick-msg');
  if (!g) { msg.textContent = 'Tap on the ground.'; return; }
  if (pickState === 'judges') {
    document.getElementById('j-lat').value = g.latLon[0].toFixed(5);
    document.getElementById('j-lon').value = g.latLon[1].toFixed(5);
    setPickStep('facing');
  } else if (pickState === 'facing') {
    const jLat = parseFloat(document.getElementById('j-lat').value), jLon = parseFloat(document.getElementById('j-lon').value);
    const dN = (g.latLon[0] - jLat) * 111320, dE = (g.latLon[1] - jLon) * 111320 * Math.cos(jLat * Math.PI / 180);
    const facing = (THREE.MathUtils.radToDeg(Math.atan2(dE, dN)) + 360) % 360;
    document.getElementById('j-hdg').value = Math.round(facing);
    const setback = units.unitToM(parseFloat(document.getElementById('j-set').value)) || DEFAULT_BOX.judgeSetbackM;
    const depth = units.unitToM(parseFloat(document.getElementById('box-d').value)) || DEFAULT_BOX.depthM;
    document.getElementById('j-set').value = Math.round(units.mToUnit(Math.max(20, Math.hypot(dN, dE) - depth / 2) || setback));
    if (placeFromJudges(msg)) setPickStep('done');
  }
});
function judgesFromInputs() {
  const lat = parseFloat(document.getElementById('j-lat').value), lon = parseFloat(document.getElementById('j-lon').value);
  return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null;
}
function worldOf(lat, lon) {
  const [e, , sth] = worldFromNed(...nedFromLla(lat, lon, originLatLon[2], originLatLon));
  return new THREE.Vector3(e, 0, sth);
}
function setPickStep(step) {
  pickState = step;
  const msg = document.getElementById('pick-msg');
  pickMarkers.clear();
  const j = judgesFromInputs();
  if (step === 'judges') msg.textContent = 'Tap where the judges stand. Drag to pan, pinch or ± to zoom.';
  else if (step === 'facing') { if (j) addPickMarker(worldOf(...j), 0xff3b30); msg.textContent = 'Now tap where the centre of the box should be.'; }
  else if (step === 'done') { msg.textContent = 'Box placed and saved. Redo to move the judges, Done to finish.'; }
}
document.getElementById('j-map').addEventListener('click', () => {
  if (!originLatLon) onOriginKnown(...(phoneFix ? [phoneFix.lat, phoneFix.lon] : HOME_FIELD));
  if (camMode !== 'map') { prevCamMode = camMode; setCamMode('map'); }
  document.getElementById('boxpanel').classList.add('hidden');
  document.getElementById('pickbar').classList.remove('hidden');
  document.body.classList.add('picking');
  const j = judgesFromInputs();
  if (j) { controls.target.copy(worldOf(...j)); camera.position.set(controls.target.x, mapCam.height, controls.target.z + 0.01); controls.update(); }
  setPickStep(j ? 'facing' : 'judges');
});
function endPick() {
  pickState = null;
  pickMarkers.clear();
  document.getElementById('pickbar').classList.add('hidden');
  document.getElementById('boxpanel').classList.remove('hidden');
  document.body.classList.remove('picking');
  if (box && box.anchor === 'judges') document.getElementById('j-msg').textContent = 'Box placed and saved.';
  if (camMode === 'map') setCamMode(prevCamMode);
}
document.getElementById('pick-done').addEventListener('click', endPick);
document.getElementById('pick-redo').addEventListener('click', () => setPickStep('judges'));
function placeFromJudges(msgEl) {
  const lat = parseFloat(document.getElementById('j-lat').value), lon = parseFloat(document.getElementById('j-lon').value);
  const facingDeg = parseFloat(document.getElementById('j-hdg').value);
  if (![lat, lon, facingDeg].every(Number.isFinite)) { msgEl.textContent = 'Need judges lat, lon and the facing direction.'; return false; }
  box = boxFromJudges({ lat, lon, facingDeg, ...readBoxInputs() });
  saveBox(box);
  fillJudgeInputs(box);
  rebuildBox();
  pickMarkers.clear();
  msgEl.textContent = 'Box placed and saved.';
  return true;
}
document.getElementById('j-place').addEventListener('click', () => placeFromJudges(document.getElementById('j-msg')));
function fillJudgeInputs(b) {
  if (!b) return;
  const [jLat, jLon] = judgeLatLon(b);
  const facing = b.judges ? b.judges.facingDeg : (b.judgeSide === 'left' ? (b.headingDeg + 90) % 360 : (b.headingDeg + 270) % 360);
  document.getElementById('j-lat').value = jLat.toFixed(5);
  document.getElementById('j-lon').value = jLon.toFixed(5);
  document.getElementById('j-hdg').value = Math.round(facing);
}
// Dimension edits re-derive the box from how it was anchored, so the judges (or the entry point) stay put.
function rederiveBox(dims) {
  if (box.anchor === 'judges' && box.judges) return boxFromJudges({ ...box.judges, ...dims });
  if (box.anchor === 'entry' && box.entry) return boxFromEntry({ ...box.entry, ...dims });
  return { ...box, ...dims };
}
fillJudgeInputs(box);
applyUnits();
document.getElementById('box-toggle').addEventListener('click', () => document.getElementById('boxpanel').classList.toggle('hidden'));
document.getElementById('box-close').addEventListener('click', () => document.getElementById('boxpanel').classList.add('hidden'));
document.getElementById('box-set').addEventListener('click', () => {
  if (!latest || !latest.init || latest.lat === undefined) { document.getElementById('a-msg').textContent = 'Needs live Hub data with the INS initialized.'; return; }
  document.getElementById('a-msg').textContent = '';
  const trackDeg = latest.gs > 15 ? latest.trk : latest.hdg;   // flight path; fall back to heading when nearly stationary
  box = boxFromEntry({ ...readBoxInputs(), lat: latest.lat, lon: latest.lon, trackDeg });
  saveBox(box);
  fillJudgeInputs(box);
  rebuildBox();
});
document.getElementById('box-clear').addEventListener('click', () => { box = null; saveBox(null); rebuildBox(); });
for (const id of Object.values(boxInputs)) {
  document.getElementById(id).addEventListener('change', () => {
    if (!box) return;
    box = rederiveBox(readBoxInputs());
    saveBox(box);
    rebuildBox();
  });
}

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

function propDiskTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, 'rgba(40,40,40,1)');
  grad.addColorStop(0.12, 'rgba(60,60,60,0.9)');
  grad.addColorStop(0.5, 'rgba(90,90,90,0.55)');
  grad.addColorStop(0.9, 'rgba(120,120,120,0.35)');
  grad.addColorStop(1, 'rgba(120,120,120,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 256, 256);
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
    add(new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.12, 16), black), 1.0, y, 0.98, Math.PI / 2, 0, 0).name = 'Front_wheel';
  }
  add(new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.06, 12), black), -2.6, 0, 0.3, Math.PI / 2, 0, 0).name = 'Rare_wheel';
  add(new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.4, 16), white), 3.05, 0, 0, 0, 0, -Math.PI / 2);
  add(new THREE.Mesh(new THREE.BoxGeometry(0.03, 1.9, 0.14), black), 2.9, 0, 0, 0.6, 0, 0);
  return g;
}
// Licensed Christen Eagle model (web/models/, not in git): cm units, Y up, nose +Z, right wing -X.
// Rotated into the FRD body frame and scaled to metres; the procedural model stands in until it loads.
const aircraft = new THREE.Group();
const propParts = { blades: [], disks: [] };
function showProp(spinning) {
  for (const m of propParts.blades) m.visible = !spinning;
  for (const d of propParts.disks) d.visible = spinning;
}
const placeholder = buildAircraft();
aircraft.add(placeholder);
scene.add(aircraft);
function loadEagleModel() {
  const path = './models/eagle/';
  new MTLLoader().setPath(path).load('eagle.mtl', (mtl) => {
    mtl.preload();
    new OBJLoader().setMaterials(mtl).setPath(path).load('eagle.obj', (obj) => {
      const props = [];
      obj.traverse((m) => {
        if (!m.isMesh) return;
        if (/canopy/i.test(m.name)) m.material = new THREE.MeshStandardMaterial({ color: 0x9fc5e8, transparent: true, opacity: 0.35, roughness: 0.1 });
        else if (/propeller/i.test(m.name)) props.push(m);
        else m.material.side = THREE.DoubleSide;
      });
      // In flight a spinning prop reads as a translucent disk at the hub (model XY plane faces +Z = nose);
      // in the hangar the blades themselves show.
      for (const m of props) {
        const bb = new THREE.Box3().setFromObject(m);
        const size = bb.getSize(new THREE.Vector3()), center = bb.getCenter(new THREE.Vector3());
        const disk = new THREE.Mesh(new THREE.CircleGeometry(Math.max(size.x, size.y) / 2, 48), new THREE.MeshBasicMaterial({
          map: propDiskTexture(), transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false,
        }));
        disk.position.copy(center);
        obj.add(disk);
        propParts.blades.push(m);
        propParts.disks.push(disk);
      }
      showProp(!hangarMode);
      const pivot = new THREE.Group();
      pivot.setRotationFromMatrix(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, -1), new THREE.Vector3(1, 0, 0)));
      pivot.scale.setScalar(0.01);
      obj.position.set(0, -1.6, -30);
      pivot.add(obj);
      aircraft.remove(placeholder);
      aircraft.add(pivot);
      settleOnWheels();
    }, undefined, (err) => console.error('eagle model failed', err));
  }, undefined, (err) => console.error('eagle mtl failed', err));
}
loadEagleModel();
// Parked pose shown until the INS is initialized and frames are flowing: all three wheels on the hangar floor.
// The stance comes from the wheel meshes of whichever model is showing, so the licensed model and the
// placeholder both sit properly.
const REST = { pos: new THREE.Vector3(0, 1.0, 0), quat: worldQuaternion(0, 10, 0) };
function wheelBox(root, pattern) {
  const toLocal = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const box = new THREE.Box3();
  root.traverse((m) => {
    if (!m.isMesh || !pattern.test(m.name)) return;
    const local = new THREE.Matrix4().multiplyMatrices(toLocal, m.matrixWorld);
    box.union(new THREE.Box3().setFromBufferAttribute(m.geometry.attributes.position).applyMatrix4(local));
  });
  return box.isEmpty() ? null : box;
}
function settleOnWheels() {
  aircraft.updateMatrixWorld(true);
  const main = wheelBox(aircraft, /front_wheel|main_wheel/i), tail = wheelBox(aircraft, /rare_wheel|rear_wheel|tail_wheel/i);
  if (!main || !tail) return;
  // Body frame (x forward, z down): pitch nose-up by θ until both wheel bottoms share one plane, then lift by that depth.
  const cm = main.getCenter(new THREE.Vector3()), ct = tail.getCenter(new THREE.Vector3());
  const rm = (main.max.z - main.min.z) / 2, rt = (tail.max.z - tail.min.z) / 2;
  const a = cm.z - ct.z, b = cm.x - ct.x, c = rt - rm, r = Math.hypot(a, b);
  if (r < 1e-6 || Math.abs(c) > r) return;
  const theta = Math.acos(c / r) - Math.atan2(b, a);
  const depth = -cm.x * Math.sin(theta) + cm.z * Math.cos(theta) + rm;
  worldQuaternion(0, THREE.MathUtils.radToDeg(theta), 0, REST.quat);
  REST.pos.set(0, depth, 0);
  if (parked) placeParked();
}
let parked = true;
settleOnWheels();
placeParked();
startPhoneLocation();

// Trail: thick screen-space line (Line2). Points are decimated to TRAIL_HZ and age out gradually.
const trailPts = new Float32Array(TRAIL_MAX * 3);
let trailLen = 0;
let trailLastMs = 0;
const trailGeo = new LineGeometry();
trailGeo.setPositions(new Float32Array(TRAIL_MAX * 3));
const trailMat = new LineMaterial({ color: 0xff7a00, linewidth: 5, worldUnits: false, transparent: true, opacity: 0.95 });
const trail = new Line2(trailGeo, trailMat);
trail.frustumCulled = false;
trailGeo.instanceCount = 0;
scene.add(trail);
const seg = trailGeo.attributes.instanceStart.data;
function writeSegment(i) {
  seg.array.set(trailPts.subarray(i * 3, i * 3 + 3), i * 6);
  seg.array.set(trailPts.subarray(i * 3 + 3, i * 3 + 6), i * 6 + 3);
}
let trailFullUpload = false;
function pushTrail(v, nowMs) {
  if (nowMs - trailLastMs < 1000 / TRAIL_HZ) return;
  trailLastMs = nowMs;
  if (trailLen === TRAIL_MAX) {
    const drop = Math.floor(TRAIL_MAX * 0.1);
    trailPts.copyWithin(0, drop * 3, trailLen * 3);
    trailLen -= drop;
    for (let i = 0; i < trailLen - 1; i += 1) writeSegment(i);
    trailFullUpload = true;
  }
  trailPts.set([v.x, v.y, v.z], trailLen * 3);
  trailLen += 1;
  if (trailLen >= 2) writeSegment(trailLen - 2);
  trailGeo.instanceCount = Math.max(0, trailLen - 1);
  // Only the new segment goes to the GPU; an empty range list means "everything", which the shift above needs.
  if (trailFullUpload || !seg.addUpdateRange) { if (seg.clearUpdateRanges) seg.clearUpdateRanges(); }
  else if (trailLen >= 2) seg.addUpdateRange((trailLen - 2) * 6, 6);
  seg.needsUpdate = true;
}
function clearTrail() { trailLen = 0; trailGeo.instanceCount = 0; }

const samples = [];
let latest = null;
let lastRecv = 0;
let socketOpen = false;
// Frames are interpolated on the Hub's own 1 ms timestamps, mapped onto the render clock, so network and
// IPC jitter (and batched delivery from the native shell) doesn't show up as motion. The offset follows the
// fastest-arriving frames and creeps upward slowly so clock skew can't accumulate; a big jump (start of a
// replay loop, long gap) resyncs.
let hubOffset = null;
function localTime(s) {
  if (!Number.isFinite(s.t)) return s.recv;
  const off = s.recv - s.t * 1000;
  if (hubOffset === null || off < hubOffset - 20 || off > hubOffset + 2000) hubOffset = off;
  else hubOffset = Math.min(off, hubOffset + 0.5);
  return s.t * 1000 + hubOffset;
}
function onSample(s, seedOnly = false) {
  s.recv = performance.now();
  s.tl = seedOnly ? s.recv : localTime(s);
  if (s.init && s.lat !== undefined) {
    if (!originLatLon) onOriginKnown(...(s.pos ? inferOrigin(s) : [s.lat, s.lon]));
    const ned = nedFromLla(s.lat, s.lon, s.alt * FT_TO_M, originLatLon);
    s.pos = worldFromNed(ned[0], ned[1], ned[2]);
  }
  if (s.pos) {
    s.v = new THREE.Vector3(s.pos[0], Math.max(0.6, s.pos[1]), s.pos[2]);
    s.q = new THREE.Quaternion(...s.quat);
    if (seedOnly) pushTrail(s.v, trailLastMs + 1000);
    if (!seedOnly) {
      const prev = samples[samples.length - 1];
      if (prev && s.tl <= prev.tl) s.tl = prev.tl + 1;
      samples.push(s);
      if (samples.length > 100) samples.splice(0, samples.length - 100);
    }
  }
  latest = s;
  lastRecv = s.recv;
}
// Origin (lat, lon) the positions are relative to, recovered from any sample carrying lat/lon + pos.
function inferOrigin(s) {
  const north = -s.pos[2], east = s.pos[0];
  const lat0 = s.lat - north / (6378137 * Math.PI / 180);
  const lon0 = s.lon - east / (6378137 * Math.PI / 180 * Math.cos(lat0 * Math.PI / 180));
  return [lat0, lon0];
}

const tmpV = new THREE.Vector3();
const tmpQ = new THREE.Quaternion();
function poseAt(t) {
  if (!samples.length) return null;
  const last = samples[samples.length - 1];
  if (t >= last.tl) return last;
  let i = samples.length - 1;
  while (i > 0 && samples[i - 1].tl > t) i -= 1;
  if (i === 0) return samples[0];
  const a = samples[i - 1], b = samples[i];
  const f = (t - a.tl) / Math.max(1, b.tl - a.tl);
  tmpV.lerpVectors(a.v, b.v, f);
  tmpQ.slerpQuaternions(a.q, b.q, f);
  return { v: tmpV, q: tmpQ };
}

// Cameras. Orbit: OrbitControls around the aircraft (pinch/wheel zooms). Chase: rigidly attached to the
// airframe — it rolls and pitches with the aircraft. Judge: fixed at the box's judging position.
let camMode = 'orbit';
let prevCamMode = 'orbit';
const mapCam = { height: 2500 };
let pickState = null;
const pickMarkers = new THREE.Group();
scene.add(pickMarkers);
const camOffset = new THREE.Vector3(8, 4, 12);
const chase = { dist: 16 };
const judge = { fov: 22, zoom: 1 };   // auto FOV keeps the aircraft a constant size; ± scales it
const DEFAULT_FOV = 55;
const bodyUp = new THREE.Vector3();
const chaseOff = new THREE.Vector3();
function setCamMode(mode) {
  camMode = mode;
  document.querySelectorAll('#controls [data-cam]').forEach(b => b.classList.toggle('on', b.dataset.cam === mode));
  applyScene();
  if (hangarMode) { hangarControls(); return; }   // in the hangar every mode orbits; the choice applies once airborne
  controls.enabled = mode === 'orbit' || mode === 'map';
  controls.enableRotate = mode !== 'map';
  controls.enablePan = mode === 'map';
  controls.screenSpacePanning = true;
  // Map mode: one finger / left button pans the map; orbit mode: they rotate.
  controls.mouseButtons.LEFT = mode === 'map' ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  controls.touches.ONE = mode === 'map' ? THREE.TOUCH.PAN : THREE.TOUCH.ROTATE;
  controls.panSpeed = mode === 'map' ? 1.6 : 1;
  controls.maxPolarAngle = mode === 'map' ? 0.001 : Math.PI;
  camera.up.set(0, 1, 0);
  if (mode !== 'judge') { camera.fov = DEFAULT_FOV; camera.updateProjectionMatrix(); }
  if (mode === 'orbit') camera.position.copy(aircraft.position).add(camOffset);
  if (mode === 'map') {
    const c = boxGroup ? judgeWorldPosition(boxGroup, new THREE.Vector3()) : aircraft.position.clone();
    controls.target.set(c.x, 0, c.z);
    camera.position.set(c.x, mapCam.height, c.z + 0.01);
    controls.update();
  }
}
function zoomBy(f) {
  if (hangarMode || camMode === 'orbit') {
    const d = camera.position.clone().sub(controls.target);
    const len = THREE.MathUtils.clamp(d.length() * f, controls.minDistance, controls.maxDistance);
    camera.position.copy(controls.target).add(d.setLength(len));
  } else if (camMode === 'chase') {
    chase.dist = THREE.MathUtils.clamp(chase.dist * f, 5, 300);
  } else if (camMode === 'judge') {
    judge.zoom = THREE.MathUtils.clamp(judge.zoom * f, 0.1, 80);
  } else if (camMode === 'map') {
    mapCam.height = THREE.MathUtils.clamp(mapCam.height * f, 200, 30000);
    camera.position.set(controls.target.x, mapCam.height, controls.target.z + 0.01);
    controls.update();
  }
}
document.querySelectorAll('#controls [data-cam]').forEach(b => b.addEventListener('click', () => setCamMode(b.dataset.cam)));
document.getElementById('clear').addEventListener('click', clearTrail);
document.getElementById('zoom-in').addEventListener('click', () => zoomBy(0.75));
document.getElementById('zoom-out').addEventListener('click', () => zoomBy(1.33));
canvas.addEventListener('wheel', (e) => { if (camMode !== 'orbit' && camMode !== 'map') { e.preventDefault(); zoomBy(Math.exp(e.deltaY * 0.0015)); } }, { passive: false });
let pinchDist = 0;
canvas.addEventListener('touchstart', (e) => { if (e.touches.length === 2) pinchDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); }, { passive: true });
canvas.addEventListener('touchmove', (e) => {
  if (camMode === 'orbit' || camMode === 'map' || e.touches.length !== 2) return;
  const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
  if (pinchDist > 0) zoomBy(pinchDist / d);
  pinchDist = d;
}, { passive: true });

function updateCamera() {
  const p = aircraft.position;
  if (boxGroup) boxGroup.userData.judgeMarker.visible = camMode !== 'judge';   // the marker would fill the judge's view
  if (hangarMode || camMode === 'orbit') {
    camera.position.sub(controls.target).add(p);
    controls.target.copy(p);
    controls.update();
  } else if (camMode === 'map') {
    controls.update();
    mapCam.height = camera.position.y;
  } else if (camMode === 'judge') {
    if (boxGroup) judgeWorldPosition(boxGroup, camera.position); else camera.position.set(0, 1.7, JUDGE_DISTANCE_M);
    camera.lookAt(p);
    const dist = Math.max(20, camera.position.distanceTo(p));
    judge.fov = THREE.MathUtils.clamp(THREE.MathUtils.radToDeg(2 * Math.atan(45 * judge.zoom / dist)), 2, 115);
    camera.fov = judge.fov;
    camera.updateProjectionMatrix();
  } else {
    chaseOff.set(-chase.dist, 0, -chase.dist * 0.28).applyQuaternion(aircraft.quaternion);
    bodyUp.set(0, 0, -1).applyQuaternion(aircraft.quaternion);
    camera.position.copy(p).add(chaseOff);
    camera.up.copy(bodyUp);
    camera.lookAt(p);
  }
}

const clamp01 = (v, lo = -0.45, hi = 1.45) => THREE.MathUtils.clamp(v, lo, hi);
const status = document.getElementById('status');
let hudNext = 0;
function setChip(text, cls) { hud.boxstat.textContent = text; hud.boxstat.className = `chip ${cls}`; }
function setMinis(st, relHdgDeg) {
  if (!st) {
    hud['plan-dot'].setAttribute('cx', '50'); hud['plan-dot'].setAttribute('cy', '50');
    hud['vert-dot'].setAttribute('cy', '50');
    hud['plan-dot'].setAttribute('class', 'mdot na');
    hud['plan-hdg'].setAttribute('class', 'mhdg na');
    hud['vert-dot'].setAttribute('class', 'mdot na');
    return;
  }
  // Top-down: judges along the bottom edge; the box spans 25..75 in both axes; outside stays visible.
  const flip = st.towardJudges < 0 ? -1 : 1;
  const px = 50 + flip * (clamp01(st.along) - 0.5) * 50;
  const py = 25 + clamp01(st.across) * 50;
  const rel = THREE.MathUtils.degToRad(relHdgDeg);
  hud['plan-dot'].setAttribute('cx', px.toFixed(1)); hud['plan-dot'].setAttribute('cy', py.toFixed(1));
  hud['plan-hdg'].setAttribute('x1', px.toFixed(1)); hud['plan-hdg'].setAttribute('y1', py.toFixed(1));
  hud['plan-hdg'].setAttribute('x2', (px + flip * 12 * Math.cos(rel)).toFixed(1));
  hud['plan-hdg'].setAttribute('y2', (py + flip * 12 * Math.sin(rel)).toFixed(1));
  // Vertical: floor at y=70, ceiling at y=30.
  hud['vert-dot'].setAttribute('cy', (70 - clamp01(st.vertical, -0.6, 1.6) * 40).toFixed(1));
  // Each indicator colours only for its own axis: horizontal position vs. altitude band.
  hud['plan-dot'].setAttribute('class', `mdot ${st.horiz ? 'out' : ''}`);
  hud['plan-hdg'].setAttribute('class', `mhdg ${st.horiz ? 'out' : ''}`);
  hud['vert-dot'].setAttribute('class', `mdot ${st.vert ? 'out' : ''}`);
}
function updateHud(now) {
  if (now < hudNext) return;
  hudNext = now + HUD_INTERVAL_MS;
  const s = latest;
  const fresh = !!s && socketOpen && now - lastRecv <= STALE_MS;
  const gps = phoneFix ? ` · phone GPS ±${units.fmtLen(phoneFix.acc)}` : '';
  let text, cls;
  if (!socketOpen) { text = `no Hub${gps}`; cls = 'bad'; }
  else if (!fresh) { text = `no data${gps}`; cls = 'bad'; }
  else if (!s.init) { text = `INS init · ${s.sats} sats`; cls = ''; }
  else if (!s.ok) { text = `INS degraded · ${s.sats} sats`; cls = ''; }
  else { text = `${s.sats} sats · ±${units.fmtLen(s.hacc * units.FT_TO_M)}`; cls = 'good'; }
  status.firstElementChild.textContent = text;
  status.className = `badge ${cls}`;
  const positioned = fresh && s.init;
  hud.nz.textContent = positioned ? s.nz.toFixed(1).padStart(4, '\u2007') : '-.-';   // room for the minus sign so the strip doesn't shift
  hud.alt.textContent = positioned ? Math.round(units.ftToUnit(s.alt)) : '----';
  // The box indicators stay up whatever the data state; without a position the dots go grey.
  hud.minis.classList.remove('hidden');
  if (!boxGroup) { setMinis(null); setChip('NO BOX', 'na'); return; }
  if (!positioned) { setMinis(null); setChip('NO POSITION', 'na'); return; }
  const st = boxStatus(boxGroup, aircraft.position);
  const parts = [st.horiz, st.vert].filter(Boolean).map((o) => `${units.fmtLenFixed(o.m)} ${o.word}`);
  setChip(parts.length ? parts.join(' · ') : 'IN BOX', parts.length ? 'out' : 'in');
  setMinis(st, s.hdg - boxGroup.userData.headingDeg);
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

if (nativeHandler) {
  const origin = new Origin(GROUND_M);
  const ingest = (b64, wall) => {
    const f = decodeIns(base64ToBytes(b64));
    if (f.init) origin.update(f);
    const s = sampleFromFrame(wall, f, origin.value);
    s.lat = f.lat; s.lon = f.lon;
    onSample(s);
  };
  window.acroReplay = {
    frame: ingest,
    frames(list) { for (let i = 0; i < list.length; i += 2) ingest(list[i], list[i + 1]); },   // [b64, wall, b64, wall, …]
    location: onPhoneFix,
    locationError(msg) {
      if (!judgesWantPhoneFix) return;
      judgesWantPhoneFix = false;
      document.getElementById('j-msg').textContent = `Location unavailable: ${msg}`;
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
  trailMat.resolution.set(w, h);
}
window.addEventListener('resize', resize);
resize();
setCamMode('orbit');
applyScene();

function frame() {
  const now = performance.now();
  const flying = socketOpen && latest && latest.init && now - lastRecv < REST_AFTER_MS;
  const pose = flying ? poseAt(now - RENDER_DELAY_MS) : null;
  if (pose) {
    if (parked) { parked = false; applyScene(); }
    aircraft.position.copy(pose.v);
    aircraft.quaternion.copy(pose.q);
    if (now - lastRecv < STALE_MS) pushTrail(pose.v, now);
  } else if (!parked) {
    parked = true;
    samples.length = 0;
    placeParked();
    applyScene();
  }
  updateCamera();
  updateHud(now);
  renderer.render(scene, camera);
  trailFullUpload = false;
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
