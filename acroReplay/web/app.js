import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { OBJLoader } from 'three/addons/OBJLoader.js';
import { MTLLoader } from 'three/addons/MTLLoader.js';
import { Line2 } from 'three/addons/Line2.js';
import { LineSegments2 } from 'three/addons/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/LineSegmentsGeometry.js';
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
import { loadFlight } from './records.js';
import { Detector, describe } from './coach/detector.js';
import { gradeFigure, critique, matchFigure, PRIMARY, PRIMARY_KNOWN } from './coach/judge.js';
import { idealFigure } from './coach/ghost.js';
import { WingRockDetector } from './coach/wingrock.js';
import { LiveCue } from './coach/livecue.js';
import { LiveCueMap } from './coach/cuemap.js';
import { POWER_KNOWNS_2026 } from './coach/knowns.js';
import { renderSequence, renderLibrary, renderFigureGrid, preload as preloadAresti } from './coach/oadraw.js';
import { flownToOlan } from './coach/flown.js';

const params = new URLSearchParams(location.search);
const GROUND_M = (parseFloat(params.get('ground_ft')) || 163) * FT_TO_M;
const TILES = params.get('tiles') !== 'none';
const JUDGE_DISTANCE_M = 700;
const RENDER_DELAY_MS = 100;
const STALE_MS = 400;
const TRAIL_HZ = 25;
const TRAIL_SECONDS_MAX = 240;   // trail buffer ceiling; the Trail length setting caps live length at or below this
const TRAIL_MAX = TRAIL_HZ * TRAIL_SECONDS_MAX;
let trailSeconds = Math.min(TRAIL_SECONDS_MAX, Math.max(5, Math.round(Number(getItem('acroReplay.trailSeconds')) || 15)));
let trailCap = TRAIL_HZ * trailSeconds;   // effective max trail points, from the user's setting
const REST_AFTER_MS = 3000;   // no frames this long → park the aircraft
const HOME_FIELD = [36.93575, -121.78975];   // KWVI, used only when nothing else says where we are
const HUD_INTERVAL_MS = 50;
const HANGAR_VIEW = new THREE.Vector3(6.5, 2.2, -7);   // orbit camera start relative to the parked aircraft
// Inside the iOS shell the native side pushes raw INS frames and phone GPS fixes instead of a bridge WebSocket.
const nativeHandler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.acro;
const nativeLog = (msg) => { if (nativeHandler) nativeHandler.postMessage(`log: ${msg}`); };

const canvas = document.getElementById('view');
const hud = Object.fromEntries(['nz', 'alt', 'alt-u', 'boxstat', 'minis', 'plan-dot', 'plan-hdg', 'vert-dot'].map(id => [id, document.getElementById(id)]));
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
const HORIZON = new THREE.Color(0xcfe0ee);
const FOG = { near: 15000, far: 170000 };
scene.fog = new THREE.Fog(HORIZON, FOG.near, FOG.far);
const FLIGHT_CLIP = { near: 1, far: 250000 };
const camera = new THREE.PerspectiveCamera(55, 1, FLIGHT_CLIP.near, FLIGHT_CLIP.far);
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

const ground = new THREE.Mesh(new THREE.PlaneGeometry(2000000, 2000000), new THREE.MeshLambertMaterial({ color: 0x6f9a5c, depthWrite: false }));
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
  document.getElementById('ground-toggle').textContent = satellite ? 'Plain' : 'Sat';
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
// Move the whole scene origin to a flight's location: the imagery (Esri/USGS tiles) and box follow it, so a
// loaded flight opens over the ground it was actually flown, not wherever the app was last originned.
function originToFlight(s) {
  if (!s || s.lat === undefined) return;
  const [lat, lon] = s.pos ? inferOrigin(s) : [s.lat, s.lon];
  if (originLatLon && Math.hypot(lat - originLatLon[0], lon - originLatLon[1]) < 5e-4) return;   // already there
  originLatLon = [lat, lon, GROUND_M];
  if (tileGround && tileGround.parent) { scene.remove(tileGround); tileGround = null; }
  ensureGround(lat, lon);
}
// Without live data the aircraft waits in the hangar; imagery, box and trail belong to the flight view.
// Map picking is the exception: it needs the ground, so it leaves the hangar while active.
function applyScene() {
  const inHangar = parked && camMode !== 'map' && !replay.active;
  if (inHangar === hangarMode) return;
  hangarMode = inHangar;
  document.body.classList.toggle('flying', !inHangar);   // gates the axes/zoom/clear controls: only live on the flight view
  hangar.visible = inHangar;
  hangar.userData.setLit(inHangar);
  trail.visible = !inHangar;
  bodyAxes.visible = axesOn && !inHangar;   // the attitude triad is a flight aid — hide it on the ground
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
document.getElementById('attribution').textContent = ATTRIBUTION;   // shown at the foot of Settings, not over the map


// Aerobatic box: set from the aircraft's live position and heading; edges and limits editable in the panel.
let box = loadBox();
let boxGroup = null;
const boxInputs = { widthM: 'box-w', depthM: 'box-d', floorFt: 'box-f', ceilFt: 'box-c', judgeAltFt: 'j-alt', judgeSide: 'box-side', judgeSetbackM: 'j-set' };
const LEN_M = new Set(['widthM', 'depthM', 'judgeSetbackM']);
const LEN_FT = new Set(['floorFt', 'ceilFt', 'judgeAltFt']);
// Judge eye height (AGL) shown in the field: an explicit override, or the default 1500 ft below the floor (>= ground).
function judgeAltEffFt(b) {
  if (b && b.judgeAltFt != null) return b.judgeAltFt;
  const floorAglFt = b && b.altRef === 'msl' ? b.floorFt - (originLatLon ? originLatLon[2] : GROUND_M) / FT_TO_M : (b ? b.floorFt : 1500);
  return Math.max(0, Math.round(floorAglFt - 1500));
}
// Box altitude reference: AGL (height above the box-centre ground, default) or MSL (absolute). Kept as a preference
// so a fresh box inherits it; the box carries its own altRef once created.
let altRefPref = getItem('acroReplay.altRef') === 'msl' ? 'msl' : 'agl';
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
    const val = k === 'judgeAltFt' ? judgeAltEffFt(b) : b[k];   // judge field shows the override or the derived default
    el.value = LEN_M.has(k) ? Math.round(units.mToUnit(val)) : LEN_FT.has(k) ? Math.round(units.ftToUnit(val)) : val;
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
  // The world datum (origin elevation) is the box-centre ground, once we know it; keeps AGL/MSL and the aircraft
  // altitude consistent. Falls back to the default field elevation until an elevation lookup fills it in.
  if (originLatLon) originLatLon[2] = (box && box.groundElevFt != null) ? box.groundElevFt * FT_TO_M : GROUND_M;
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
// Box placement sub-tabs (From aircraft / From judges)
document.querySelectorAll('.ptab[data-mode]').forEach((tab) => tab.addEventListener('click', () => {
  document.querySelectorAll('.ptab[data-mode]').forEach((b) => b.classList.toggle('on', b === tab));
  document.getElementById('mode-aircraft').classList.toggle('hidden', tab.dataset.mode !== 'aircraft');
  document.getElementById('mode-judges').classList.toggle('hidden', tab.dataset.mode !== 'judges');
}));
// Top-level panel tabs: Box vs Settings
const PANEL_TITLES = { box: 'Box', settings: 'Settings', sequences: 'Sequences' };
function showPanelTab(name) {
  document.querySelectorAll('.ptab[data-panel]').forEach((b) => b.classList.toggle('on', b.dataset.panel === name));
  document.getElementById('panel-box').classList.toggle('hidden', name !== 'box');
  document.getElementById('panel-settings').classList.toggle('hidden', name !== 'settings');
  document.getElementById('panel-sequences').classList.toggle('hidden', name !== 'sequences');
  document.getElementById('panel-title').textContent = PANEL_TITLES[name] || 'Box';
  if (name === 'sequences') preloadAresti();   // warm the Aresti engine when the tab opens
}
document.querySelectorAll('.ptab[data-panel]').forEach((tab) => tab.addEventListener('click', () => showPanelTab(tab.dataset.panel)));
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
// A pick tap must be one finger, barely moved, and quick — so panning, pinch-zoom, or a slow drag never places.
let pickDown = null;      // [x, y, t] of the first finger down
let pickPointers = 0;     // fingers currently down
let pickMulti = false;    // more than one finger touched during this gesture
canvas.addEventListener('pointerdown', (e) => {
  pickPointers += 1;
  if (pickPointers > 1) { pickMulti = true; return; }
  pickMulti = false;
  pickDown = [e.clientX, e.clientY, performance.now()];
});
const endPickPointer = () => { pickPointers = Math.max(0, pickPointers - 1); };
canvas.addEventListener('pointercancel', endPickPointer);
canvas.addEventListener('pointerup', (e) => {
  const last = pickPointers <= 1;   // this is the final finger lifting
  const wasMulti = pickMulti;
  endPickPointer();
  if (!last) return;
  const tap = !wasMulti && pickDown
    && Math.hypot(e.clientX - pickDown[0], e.clientY - pickDown[1]) <= 12
    && performance.now() - pickDown[2] <= 600;
  pickDown = null;
  if (!pickState || pickState === 'done' || !tap) return;
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
    pickBoxCenter = g.world.clone();   // remember the tapped box centre so it can be marked
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
  if (step === 'judges') { pickBoxCenter = null; msg.textContent = 'Tap where the judges stand. Drag to pan, pinch or ± to zoom.'; }
  else if (step === 'facing') { if (j) addPickMarker(worldOf(...j), 0xff3b30); msg.textContent = 'Now tap where the centre of the box should be.'; }
  else if (step === 'done') {
    if (j) addPickMarker(worldOf(...j), 0xff3b30);            // judge (red)
    if (pickBoxCenter) addPickMarker(pickBoxCenter, 0x3b82f6);   // box centre (blue)
    msg.textContent = 'Box placed and saved. Redo to move the judges, Done to finish.';
  }
}
document.getElementById('j-map').addEventListener('click', () => {
  if (!originLatLon) onOriginKnown(...(phoneFix ? [phoneFix.lat, phoneFix.lon] : HOME_FIELD));
  if (camMode !== 'map') { prevCamMode = camMode; setCamMode('map'); }
  document.getElementById('boxpanel').classList.add('hidden');
  document.getElementById('pickbar').classList.remove('hidden');
  document.body.classList.add('picking');
  pickPointers = 0; pickMulti = false; pickDown = null;   // clean tap state on entry
  const j = judgesFromInputs();
  if (j) { controls.target.copy(worldOf(...j)); camera.position.set(controls.target.x, mapCam.height, controls.target.z + 0.01); controls.update(); }
  setPickStep('judges');   // always place the judge first, even if a previous position is on file
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
  box = boxFromJudges({ lat, lon, facingDeg, altRef: altRefPref, ...readBoxInputs() });
  saveBox(box);
  fillJudgeInputs(box);
  rebuildBox();
  updateBoxGroundElev();
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
document.getElementById('settings-toggle').addEventListener('click', () => {
  const panel = document.getElementById('boxpanel');
  const opening = panel.classList.contains('hidden');
  panel.classList.toggle('hidden');
  if (opening) showPanelTab('settings');   // the gear always lands on Settings
});
document.getElementById('box-close').addEventListener('click', () => document.getElementById('boxpanel').classList.add('hidden'));
// Tapping the empty 3D scene closes any open pop-over (the Box panel and the coach card); the replay bar and
// the pick bar are active tools and stay. Called from the canvas tap handler.
function closeMenus() {
  document.getElementById('boxpanel').classList.add('hidden');
}
document.addEventListener('pointerdown', (e) => {
  const bp = document.getElementById('boxpanel');
  if (!bp.classList.contains('hidden') && !bp.contains(e.target) && !e.target.closest('#settings-toggle')) bp.classList.add('hidden');
  // Tapping the scene (outside the replay bar) collapses the expanded Figures list.
  const rl = document.getElementById('rb-list'), rbar = document.getElementById('replaybar');
  if (rl && !rl.classList.contains('hidden') && !rbar.contains(e.target)) rl.classList.add('hidden');
}, true);
document.getElementById('box-set').addEventListener('click', () => {
  if (!latest || !latest.init || latest.lat === undefined) { document.getElementById('a-msg').textContent = 'Needs live Hub data with the INS initialized.'; return; }
  document.getElementById('a-msg').textContent = '';
  const trackDeg = latest.gs > 15 ? latest.trk : latest.hdg;   // flight path; fall back to heading when nearly stationary
  box = boxFromEntry({ altRef: altRefPref, ...readBoxInputs(), lat: latest.lat, lon: latest.lon, trackDeg });
  saveBox(box);
  fillJudgeInputs(box);
  rebuildBox();
  updateBoxGroundElev();
});
document.getElementById('box-clear').addEventListener('click', () => { box = null; saveBox(null); rebuildBox(); });
// Look up the box-centre ground elevation (MSL) and adopt it as the world datum, so AGL/MSL and the aircraft's
// altitude line up with the real field. Cached on the box; falls back silently to the default field elevation.
async function updateBoxGroundElev() {
  if (!box || !Number.isFinite(box.lat) || !Number.isFinite(box.lon)) return;
  try {
    const r = await fetch(`https://api.open-meteo.com/v1/elevation?latitude=${box.lat.toFixed(5)}&longitude=${box.lon.toFixed(5)}`);
    const j = await r.json();
    const m = Array.isArray(j.elevation) ? j.elevation[0] : (typeof j.elevation === 'number' ? j.elevation : NaN);
    if (!Number.isFinite(m) || !box) return;
    box.groundElevFt = m / FT_TO_M;
    saveBox(box);
    replaceLoadedSamples();   // rebuildBox() adopts the new datum; re-place any loaded flight against it
    rebuildBox();
  } catch (e) { nativeLog(`elevation lookup failed: ${e.message || e}`); }
}
// Re-place already-loaded samples (a replay, or live history) after the world datum changes, and refill the trail.
function replaceLoadedSamples() {
  if (!originLatLon) return;
  for (const s of replay.samples || []) if (s.lat !== undefined) placeSample(s);
  for (const s of history || []) if (s.lat !== undefined) placeSample(s);
  if (replay.active) seekTo(replay.cursor);
}
for (const [k, id] of Object.entries(boxInputs)) {
  document.getElementById(id).addEventListener('change', () => {
    if (!box) return;
    box = rederiveBox(readBoxInputs());
    if (k === 'floorFt') box.judgeAltFt = null;   // floor changed -> let the judge re-derive to 1500 below the new floor
    saveBox(box);
    rebuildBox();
    if (k === 'floorFt') writeBoxInputs(box);      // show the refreshed judge default
  });
}
// AGL/MSL toggle: switch the reference the box floor/ceiling are entered in, converting the numbers by the
// box-centre ground elevation so the box itself stays put.
function markAltRef(ref) { document.querySelectorAll('#alt-ref [data-altref]').forEach((b) => b.classList.toggle('on', b.dataset.altref === ref)); }
document.querySelectorAll('#alt-ref [data-altref]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const ref = btn.dataset.altref;
    if (ref === altRefPref) return;
    const groundFt = Math.round((originLatLon ? originLatLon[2] : GROUND_M) / FT_TO_M);
    if (box) {
      const delta = ref === 'msl' ? groundFt : -groundFt;   // AGL->MSL adds the ground elevation; MSL->AGL removes it
      box.floorFt += delta; box.ceilFt += delta; box.altRef = ref;
      saveBox(box); writeBoxInputs(box); rebuildBox();
    }
    altRefPref = ref; setItem('acroReplay.altRef', ref);
    markAltRef(ref);
  });
});
markAltRef((box && box.altRef) || altRefPref);

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

// Licensed aircraft models (web/models/, not in git). Every OBJ is Y up, nose +Z, right wing -X; `scale`
// takes its units to metres and `offset` (model units) puts its origin on the CG. Mesh names carry the roles:
// canopy (glass), propeller (blades → spinning disk), main_wheels / tail_wheel (parked stance).
// Rotated into the FRD body frame; nothing is drawn until the picked model has loaded.
const MODELS = {
  eagle: { dir: 'eagle', scale: 0.01, offset: [0, -1.6, -30] },
  extra: { dir: 'extra', scale: 1, offset: [0, 0, 0] },
  rv7: { dir: 'rv7', scale: 1, offset: [0, 0, 0] },
};
const aircraft = new THREE.Group();
// Principal (body) axes drawn from the CG, in the FRD frame this app flies in: X forward = red, Y right = green,
// Z down = blue (the typical RGB→XYZ convention). Solid unlit arrows so they read clearly against the scene.
// Toggled from Settings; re-added after every model swap because showModel() clears the group.
let axesOn = getItem('acroReplay.axes') !== 'off';
function makeAxisLine(dir, color) {
  const len = 4.4, r = 0.18;   // thick unlit rod, no arrowhead
  const rod = new THREE.Mesh(new THREE.CylinderGeometry(r, r, len, 14), new THREE.MeshBasicMaterial({ color }));
  rod.position.y = len / 2;
  const g = new THREE.Group();
  g.add(rod);
  g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);   // cylinders point +Y by default
  return g;
}
const bodyAxes = new THREE.Group();
bodyAxes.add(makeAxisLine(new THREE.Vector3(1, 0, 0), 0xff3b30));   // X forward, red
bodyAxes.add(makeAxisLine(new THREE.Vector3(0, 1, 0), 0x2ecc40));   // Y right, green
bodyAxes.add(makeAxisLine(new THREE.Vector3(0, 0, 1), 0x3b82f6));   // Z down, blue
bodyAxes.visible = false;   // shown only in flight (applyScene gates on hangar state)
// Grey reference lines centred on the aircraft but held in the box's orientation (they don't roll with the plane),
// so the pilot can read attitude against the box axes. Each is a rod through the origin (both directions).
function makeBoxLine(dir) {
  const half = 5.5, r = 0.11;
  const rod = new THREE.Mesh(new THREE.CylinderGeometry(r, r, half * 2, 12),
    new THREE.MeshBasicMaterial({ color: 0xc2c8d0, transparent: true, opacity: 0.7 }));
  const g = new THREE.Group();
  g.add(rod);
  g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  return g;
}
const boxAxes = new THREE.Group();
boxAxes.add(makeBoxLine(new THREE.Vector3(1, 0, 0)));   // along the box front edge
boxAxes.add(makeBoxLine(new THREE.Vector3(0, 1, 0)));   // box vertical
boxAxes.add(makeBoxLine(new THREE.Vector3(0, 0, 1)));   // box depth
boxAxes.visible = false;
scene.add(boxAxes);
const propParts = { blades: [], disks: [] };
function showProp(spinning) {
  for (const m of propParts.blades) m.visible = !spinning;
  for (const d of propParts.disks) d.visible = spinning;
}
let modelKey = MODELS[getItem('acroReplay.model')] ? getItem('acroReplay.model') : 'eagle';
let shownKey = null;       // model actually on screen (differs from modelKey while a pick is loading)
let modelGeneration = 0;   // bumps on every pick; a load that finishes for an older generation is dropped
scene.add(aircraft);
const modelMsg = document.getElementById('model-msg');
// The aircraft group holds exactly one model; the old one stays up until its replacement has loaded.
function showModel(node, key) {
  aircraft.clear();
  aircraft.add(node);
  shownKey = key;
  settleOnWheels();          // stance is measured from the model's own meshes...
  aircraft.add(bodyAxes);    // ...then re-add the axes (kept out of that measurement, and off the cleared group)
}
function markModelButtons() {
  document.querySelectorAll('#model [data-model]').forEach((btn) => btn.classList.toggle('on', btn.dataset.model === modelKey));
}
function loadAircraftModel(key) {
  const { dir, scale, offset } = MODELS[key];
  const path = `./models/${dir}/`;
  const generation = modelGeneration;
  const failed = (what) => (err) => {
    nativeLog(`model ${key} ${what} failed: ${err && (err.message || err.type || err)}`);
    if (generation !== modelGeneration) return;
    modelMsg.textContent = `Couldn't load the ${dir} model${shownKey ? `; keeping the ${MODELS[shownKey].dir}` : ''}.`;
    if (shownKey) { modelKey = shownKey; setItem('acroReplay.model', shownKey); markModelButtons(); }
  };
  new MTLLoader().setPath(path).load(`${dir}.mtl`, (mtl) => {
    mtl.preload();
    new OBJLoader().setMaterials(mtl).setPath(path).load(`${dir}.obj`, (obj) => {
      if (generation !== modelGeneration) { nativeLog(`model ${key} loaded but superseded by ${modelKey}`); return; }
      nativeLog(`model ${key} shown`);
      modelMsg.textContent = '';
      const props = [];
      obj.traverse((m) => {
        if (!m.isMesh) return;
        if (/canopy/i.test(m.name)) m.material = new THREE.MeshStandardMaterial({ color: 0x9fc5e8, transparent: true, opacity: 0.35, roughness: 0.1 });
        else if (/propeller/i.test(m.name)) props.push(m);
        else m.material.side = THREE.DoubleSide;
      });
      // In flight a spinning prop reads as a translucent disk at the hub (model XY plane faces +Z = nose);
      // in the hangar the blades themselves show.
      propParts.blades = props;
      propParts.disks = [];
      if (props.length) {
        const bb = new THREE.Box3();
        for (const m of props) bb.expandByObject(m);
        const size = bb.getSize(new THREE.Vector3()), center = bb.getCenter(new THREE.Vector3());
        const disk = new THREE.Mesh(new THREE.CircleGeometry(Math.max(size.x, size.y) / 2, 48), new THREE.MeshBasicMaterial({
          map: propDiskTexture(), transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false,
        }));
        disk.position.copy(center);
        obj.add(disk);
        propParts.disks.push(disk);
      }
      showProp(!hangarMode);
      const pivot = new THREE.Group();
      pivot.setRotationFromMatrix(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, -1), new THREE.Vector3(1, 0, 0)));
      pivot.scale.setScalar(scale);
      obj.position.fromArray(offset);
      pivot.add(obj);
      showModel(pivot, key);
    }, undefined, failed('model'));
  }, undefined, failed('materials'));
}
function setModel(key) {
  nativeLog(`model pick ${key} (was ${modelKey})`);
  modelKey = key;
  modelGeneration += 1;
  setItem('acroReplay.model', key);
  markModelButtons();
  modelMsg.textContent = `Loading the ${MODELS[key].dir}…`;
  loadAircraftModel(key);
}
document.querySelectorAll('#model [data-model]').forEach((btn) => {
  btn.addEventListener('click', () => { if (btn.dataset.model !== modelKey) setModel(btn.dataset.model); });
});
markModelButtons();
loadAircraftModel(modelKey);
// Parked pose shown until the INS is initialized and frames are flowing: all three wheels on the hangar floor.
// The stance comes from the model's own wheel meshes once it has loaded.
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
// Lowest point (largest body z) of the model aft of `xMax`, in the body frame — where a tail skid or an
// unmodelled tail wheel would hang from.
function lowestPointAft(root, xMax) {
  const toLocal = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const v = new THREE.Vector3(), local = new THREE.Matrix4();
  let best = null;
  root.traverse((m) => {
    if (!m.isMesh) return;
    local.multiplyMatrices(toLocal, m.matrixWorld);
    const pos = m.geometry.attributes.position;
    for (let i = 0; i < pos.count; i += 1) {
      v.fromBufferAttribute(pos, i).applyMatrix4(local);
      if (v.x < xMax && (!best || v.z > best.z)) best = v.clone();
    }
  });
  return best;
}
const TAILWHEEL_M = 0.45;   // tail-cone height above the floor for a taildragger whose model has no tail wheel
function settleOnWheels() {
  aircraft.updateMatrixWorld(true);
  const main = wheelBox(aircraft, /front_wheel|main_wheel/i), tail = wheelBox(aircraft, /rare_wheel|rear_wheel|tail_wheel/i);
  if (!main) return;
  const cm = main.getCenter(new THREE.Vector3());
  const rm = (main.max.z - main.min.z) / 2;
  let ct, rt;
  if (tail) {
    ct = tail.getCenter(new THREE.Vector3());
    rt = (tail.max.z - tail.min.z) / 2;
  } else {
    // Mains well ahead of the body origin: a taildragger missing its tail wheel — hang the tail cone at
    // tail-wheel height. Otherwise tricycle gear: level, mains on the floor.
    const aft = cm.x > 0.2 ? lowestPointAft(aircraft, cm.x - 1.5) : null;
    if (!aft) {
      worldQuaternion(0, 0, 0, REST.quat);
      REST.pos.set(0, main.max.z, 0);
      hangar.userData.placeChocks(main.max.y - 0.1, cm.x + rm + 0.2);
      if (parked) placeParked();
      return;
    }
    ct = new THREE.Vector3(aft.x, 0, aft.z + TAILWHEEL_M);
    rt = 0;
  }
  // Body frame (x forward, z down): pitch nose-up by θ until both contact points share one plane, then lift by that depth.
  const a = cm.z - ct.z, b = cm.x - ct.x, c = rt - rm, r = Math.hypot(a, b);
  if (r < 1e-6 || Math.abs(c) > r) return;
  const theta = Math.acos(c / r) - Math.atan2(b, a);
  const depth = -cm.x * Math.sin(theta) + cm.z * Math.cos(theta) + rm;
  worldQuaternion(0, THREE.MathUtils.radToDeg(theta), 0, REST.quat);
  REST.pos.set(0, depth, 0);
  hangar.userData.placeChocks(main.max.y - 0.1, cm.x * Math.cos(theta) + cm.z * Math.sin(theta) + rm + 0.2);
  if (parked) placeParked();
}
let parked = true;
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
// `force` appends without the 25 Hz gate and without touching the live clock (history seeding, replay refill).
function pushTrail(v, nowMs, force = false) {
  if (!force) {
    if (nowMs - trailLastMs < 1000 / TRAIL_HZ) return;
    trailLastMs = nowMs;
  }
  if (trailLen >= trailCap) {
    const drop = Math.max(1, Math.floor(trailCap * 0.1));
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
function clearTrail() { trailLen = 0; trailGeo.instanceCount = 0; trailLastMs = 0; if (seg.clearUpdateRanges) seg.clearUpdateRanges(); }
// User-set trail length (seconds). Lowering it trims the oldest points at once so the change is visible immediately.
function setTrailSeconds(s) {
  trailSeconds = Math.min(TRAIL_SECONDS_MAX, Math.max(5, Math.round(s) || 15));
  trailCap = TRAIL_HZ * trailSeconds;
  setItem('acroReplay.trailSeconds', String(trailSeconds));
  if (trailLen > trailCap) {
    const drop = trailLen - trailCap;
    trailPts.copyWithin(0, drop * 3, trailLen * 3);
    trailLen -= drop;
    for (let i = 0; i < trailLen - 1; i += 1) writeSegment(i);
    trailGeo.instanceCount = Math.max(0, trailLen - 1);
    trailFullUpload = true;
  }
}

const samples = [];
let latest = null;
let lastRecv = 0;
let socketOpen = false;
// Everything received in the last 20 minutes, for "last figure" replay; the live detector segments it as it comes.
const HISTORY_MAX = 20 * 60 * 50;
const history = [];
const liveDetector = new Detector((fig) => onFigureDetected(fig, 'live'));
const wingRock = new WingRockDetector((r) => onWingRock(r));   // entry/exit rock brackets a scored routine
function placeSample(s) {
  if (!(s.init && s.lat !== undefined)) return false;
  if (!originLatLon) onOriginKnown(...(s.pos ? inferOrigin(s) : [s.lat, s.lon]));
  const ned = nedFromLla(s.lat, s.lon, s.alt * FT_TO_M, originLatLon);
  s.pos = worldFromNed(ned[0], ned[1], ned[2]);
  s.v = new THREE.Vector3(s.pos[0], Math.max(0.6, s.pos[1]), s.pos[2]);
  s.q = new THREE.Quaternion(...s.quat);
  return true;
}
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
  placeSample(s);
  if (s.init && s.quat) {
    history.push(s);
    if (history.length > HISTORY_MAX) history.splice(0, history.length - HISTORY_MAX);
    if (!seedOnly) { liveDetector.push(s); wingRock.push(s); }
  }
  if (s.pos) {
    if (seedOnly) pushTrail(s.v, 0, true);
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

// Replay: scrub through a loaded flight file or the live history; the detector's figures become markers on
// the bar and rows in the label list. Times are Hub seconds (sample.t).
const replay = { active: false, playing: false, speed: 1, samples: [], cursor: 0, t0: 0, t1: 0, current: null, figures: [], name: '', lastNow: 0, loop: null };
const rb = Object.fromEntries(['replaybar', 'rb-play', 'rb-scrub', 'rb-time', 'rb-speed', 'rb-marks', 'rb-flight', 'rb-load', 'rb-last', 'rb-list', 'rb-toggle-list', 'rb-save']
  .map((id) => [id, document.getElementById(id)]));
const FIGURE_TYPES = ['loop', 'spin', 'half cuban', '45 up line', '180 turn', 'slow roll', 'immelmann', 'hammerhead', 'split-s', 'humpty', 'other'];
// Per-figure "modifier": the one number that changes a figure's meaning (a spin's expected turns). Keyed by the
// figure type; extend as more figures gain parameters. `def` supplies the default shown until the pilot overrides.
const MODIFIERS = { spin: { key: 'turns', label: 'Turns', min: 0.25, step: 0.25, def: () => spinTurns } };
const cap = (x) => (x ? x.replace(/^\w/, (c) => c.toUpperCase()) : x);
let labels = {};   // t0 (rounded) → { type, grade, notes }
const rV = new THREE.Vector3(), rQ = new THREE.Quaternion();
function fmtClock(sec) { const m = Math.floor(sec / 60), s2 = Math.floor(sec % 60); return `${m}:${String(s2).padStart(2, '0')}`; }
function replayIndex(t) {
  const a = replay.samples; let lo = 0, hi = a.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid].t < t) lo = mid + 1; else hi = mid; }
  return lo;
}
function replayTick(now) {
  const before = replay.cursor;
  if (replay.playing) {
    replay.cursor += ((now - replay.lastNow) / 1000) * replay.speed;
    const end = replay.loop ? replay.loop.t1 + 0.25 : replay.t1;   // small hold, then restart before the next figure
    if (replay.cursor >= end) {
      if (replay.loop) { replay.cursor = replay.loop.t0; clearTrail(); }   // loop this figure, trail from scratch
      else { replay.cursor = replay.t1; setPlaying(false); }
    }
    // Whole-sequence playback: clear the trail as each figure completes, so every manoeuvre draws its own.
    if (!replay.loop && replay.cursor > before && replay.figures.some((f) => f.grade && before < f.t1 && replay.cursor >= f.t1)) clearTrail();
  }
  replay.lastNow = now;
  // Show the figure's name, score and ghost from the moment the cursor reaches its entry (t0), and hold them
  // through the figure and a couple of seconds after, so you watch the figure knowing what it scored.
  let k;
  if (replay.loop) k = replay.loop.k;
  else {
    // The figure the cursor is inside; else the most recent one it just finished (so the card lingers briefly).
    k = replay.figures.findIndex((fig) => fig.grade && replay.cursor >= fig.t0 - 0.5 && replay.cursor <= fig.t1 + 0.5);
    if (k < 0) for (let i = replay.figures.length - 1; i >= 0; i -= 1) { const f = replay.figures[i]; if (f.grade && replay.cursor > f.t1 && replay.cursor <= f.t1 + 2.5) { k = i; break; } }
  }
  if (k >= 0) {
    if (k !== replay.lastShown) { replay.lastShown = k; showCoach(replay.figures[k].grade); highlightRow(k); }
    showGhost(replay.figures[k], replay.samples);
  } else {
    replay.lastShown = -1;
    if (ghostFor) clearGhost();
  }
  const a = replay.samples;
  if (!a.length) return null;
  const i = Math.min(a.length - 1, replayIndex(replay.cursor));
  const b = a[i], prev = a[Math.max(0, i - 1)];
  replay.current = b;
  if (now >= hudNext) { rb['rb-scrub'].value = Math.round(((replay.cursor - replay.t0) / Math.max(1, replay.t1 - replay.t0)) * 1000); rb['rb-time'].textContent = fmtClock(replay.cursor - replay.t0); }
  if (!b.v) return prev.v ? { v: prev.v, q: prev.q } : null;
  if (!prev.v || prev === b) return { v: b.v, q: b.q };
  const f = THREE.MathUtils.clamp((replay.cursor - prev.t) / Math.max(1e-3, b.t - prev.t), 0, 1);
  rV.lerpVectors(prev.v, b.v, f); rQ.slerpQuaternions(prev.q, b.q, f);
  return { v: rV, q: rQ };
}
const PLAY_SVG = '<svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5l9 5.5-9 5.5z" fill="currentColor"/></svg>';
const PAUSE_SVG = '<svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/><rect x="9.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/></svg>';
function setPlaying(on) { replay.playing = on; rb['rb-play'].innerHTML = on ? PAUSE_SVG : PLAY_SVG; rb['rb-play'].setAttribute('aria-label', on ? 'pause' : 'play'); }
function seekTo(t, refillTrail = true) {
  replay.cursor = THREE.MathUtils.clamp(t, replay.t0, replay.t1);
  replay.lastNow = performance.now();
  if (!refillTrail) return;
  clearTrail();
  const lower = replay.loop ? Math.max(replay.loop.t0, replay.cursor - 40) : replay.cursor - 40;
  const from = replayIndex(lower), to = replayIndex(replay.cursor);
  for (let i = from; i <= to; i += 2) { const s = replay.samples[i]; if (s.v) pushTrail(s.v, 0, true); }
}
function startReplay(samples, name, at, figures, flightBox) {
  const placed = samples.filter((s) => s.init && s.quat);
  if (!placed.length) { rb['rb-time'].textContent = 'no INS data'; return; }
  // Re-origin to this flight so the satellite imagery, ground and box are placed at where it was flown.
  originToFlight(placed.find((s) => s.lat !== undefined) || placed[0]);
  if (flightBox) { box = { ...DEFAULT_BOX, ...flightBox }; saveBox(box); fillJudgeInputs(box); if (box.groundElevFt == null) updateBoxGroundElev(); }
  rebuildBox();
  for (const s of placed) placeSample(s);
  replay.samples = placed; replay.name = name;
  replay.t0 = placed[0].t; replay.t1 = placed[placed.length - 1].t;
  replay.figures = figures || Detector.run(placed);
  restoreLabels(name);
  for (const fig of replay.figures) fig.grade = gradeOne(fig);
  resetRun();
  replay.lastShown = -1;
  replay.active = true;
  setPlaying(false);
  rb.replaybar.classList.remove('hidden');
  document.body.classList.add('replaying');
  setReplayLabel();
  if (camMode === 'orbit') setCamMode('orbit');   // enable orbit pan for review
  renderMarks(); renderList();
  replay.loop = null;
  seekTo(at !== undefined ? at : (replay.figures[0] ? replay.figures[0].t0 - 2 : replay.t0));
  applyScene();
  updateCamera();
}
function regradeReplay() {
  if (!replay.active) return;   // the live coach path re-grades on the next figure on its own
  for (const fig of replay.figures) fig.grade = gradeOne(fig);
  replay.lastShown = -1;   // force the frame loop to refresh the card and ghost with the new grades
  renderMarks(); renderList();
}
// The Replay button doubles as Live, like Sat/Plain: it reads 'Replay' in live view and 'Live' while the replay
// panel is up, and tapping it returns to live.
function setReplayLabel() {
  const open = !rb.replaybar.classList.contains('hidden');
  document.getElementById('replay-toggle').textContent = open ? 'Live' : 'Replay';
  document.body.classList.toggle('rbopen', open);   // panel open -> lift the zoom/settings stack clear of it
}
function stopReplay() {
  replay.active = false; setPlaying(false);
  clearGhost();
  if (camMode === 'orbit' || camMode === 'free') setCamMode('orbit');   // re-lock orbit, and rescue a stuck Free view
  rb.replaybar.classList.add('hidden');
  document.body.classList.remove('replaying');
  clearTrail();
  resetRun();
  applyScene();
  setReplayLabel();
}
// Real-time simulation: play a saved flight THROUGH the live pipeline (onSample), so figures are recognised and
// scored only as they complete — exactly as they would live, nothing known ahead — rather than the pre-scored
// replay. Lets us test the real-time coaching from a recorded clip with no Hub connected.
let sim = null;
async function startSim(name) {
  if (!name) return;
  if (replay.active) stopReplay();
  rb['rb-time'].textContent = 'loading\u2026';
  let raw;
  try { ({ samples: raw } = await loadFlight(`/flights/${encodeURIComponent(name)}`)); }
  catch (e) { rb['rb-time'].textContent = String(e.message || e); return; }
  const placed = raw.filter((s) => s.init && s.quat);
  if (!placed.length) { rb['rb-time'].textContent = 'no INS data'; return; }
  samples.length = 0; history.length = 0; hubOffset = null; latest = null; lastRecv = 0; originLatLon = null;
  liveDetector.reset(); wingRock.reset(); resetRun();
  clearTrail(); clearGhost(); coachCard.classList.add('hidden');
  document.body.classList.remove('replaying');
  rb.replaybar.classList.remove('hidden');
  document.body.classList.add('simming');   // a sim mirrors real-time flight: hide the scrubber/transport chrome
  setReplayLabel();
  sim = { samples: placed, i: 0, t0: placed[0].t, clock: placed[0].t, lastNow: performance.now() };
  document.getElementById('rb-sim').textContent = 'Stop sim';
  rb['rb-time'].textContent = 'live sim';
}
function simFeed(now) {
  sim.clock += ((now - sim.lastNow) / 1000) * replay.speed;   // the transport speed control drives the sim too
  sim.lastNow = now;
  while (sim.i < sim.samples.length && sim.samples[sim.i].t <= sim.clock) { onSample(sim.samples[sim.i]); sim.i += 1; }
  if (sim.i >= sim.samples.length) stopSim();
}
function stopSim() {
  if (!sim) return;
  sim = null;
  liveDetector.reset(); wingRock.reset(); resetRun();
  latest = null; lastRecv = 0;   // drop the sim's last frame so the view returns to live (or the hangar) at once
  document.getElementById('rb-sim').textContent = 'Sim';
  rb['rb-time'].textContent = '0:00';
  rb.replaybar.classList.add('hidden');
  document.body.classList.remove('simming');
  document.body.classList.remove('replaying');
  if (camMode === 'orbit' || camMode === 'free') setCamMode('orbit');   // never leave the pilot stuck in the free/sky view
  setReplayLabel();
}
function renderMarks() {
  rb['rb-marks'].innerHTML = '';
  const span = Math.max(1, replay.t1 - replay.t0);
  replay.figures.forEach((fig, k) => {
    const m = document.createElement('button');
    m.className = 'mark';
    m.setAttribute('aria-label', `figure ${k + 1}`);
    m.style.left = `${((fig.t0 - replay.t0) / span) * 100}%`;
    m.style.width = `${Math.max(0.4, ((fig.t1 - fig.t0) / span) * 100)}%`;
    m.title = `${k + 1}: ${gradeText(fig.grade)}${fig.elements.map(describe).join(' · ')}`;
    if (fig.grade) m.classList.add('scored');
    m.addEventListener('click', () => showFigure(k));
    rb['rb-marks'].appendChild(m);
  });
}
function labelKey(fig) { return String(Math.round(fig.t0)); }
function renderList() {
  const list = rb['rb-list'];
  list.innerHTML = '';
  replay.figures.forEach((fig, k) => {
    const lab = labels[labelKey(fig)] || {};
    const g = fig.grade;
    const autoType = g ? g.type : 'other';
    const chosen = lab.type || autoType;                 // the dropdown shows what the figure is being graded as
    const scoreTxt = g ? (g.hz ? 'HZ' : g.score.toFixed(1)) : '\u2014';
    const opts = FIGURE_TYPES.map((t2) => `<option value="${t2}"${chosen === t2 ? ' selected' : ''}>${t2}</option>`).join('');
    const mod = MODIFIERS[chosen];
    const modCtl = mod
      ? `<label class="lfield lmodwrap">${mod.label}<input class="lmod" data-key="${mod.key}" type="number" min="${mod.min}" step="${mod.step}" value="${lab[mod.key] ?? mod.def()}"></label>`
      : '';
    const row = document.createElement('div');
    row.className = 'lrow'; row.dataset.k = k;
    row.innerHTML =
        `<div class="lhead"><button class="lgo">${k + 1}</button><span class="lt">${fmtClock(fig.t0 - replay.t0)}</span>`
      +   `<span class="lname">${cap(autoType)}</span><span class="lscorewrap"><span class="lscorelbl">auto</span><span class="lscore${g && g.hz ? ' hz' : ''}">${scoreTxt}</span></span></div>`
      + `<div class="lbreak">${fig.elements.map(describe).join(' \u00b7 ')}</div>`
      + `<div class="lctl"><label class="lfield">Type<select class="ltype">${opts}</select></label>${modCtl}</div>`;
    const applyOverride = () => {
      const modEl = row.querySelector('.lmod');
      const next = { ...(labels[labelKey(fig)] || {}), type: row.querySelector('.ltype').value };
      if (modEl) { const v = parseFloat(modEl.value); if (Number.isFinite(v)) next[modEl.dataset.key] = v; }
      labels[labelKey(fig)] = next;
      fig.grade = gradeOne(fig);            // re-score against the declared type and modifier
      persistLabels();                      // keep the override across a reload of this flight
      clearGhost();                         // the ideal overlay is cached per figure — force it to rebuild
      renderMarks(); renderList();          // refresh this row's readout and the timeline mark colours
      if (replay.loop && replay.figures[replay.loop.k] === fig && fig.grade) showCoach(fig.grade);
    };
    row.querySelector('.lgo').addEventListener('click', () => showFigure(k));
    for (const el of row.querySelectorAll('.ltype, .lmod')) el.addEventListener('change', applyOverride);
    list.appendChild(row);
  });
}
function highlightRow(k) { rb['rb-list'].querySelectorAll('.lrow').forEach((r) => r.classList.toggle('on', Number(r.dataset.k) === k)); }
function loopFigure(fig, k) {
  replay.loop = { t0: fig.t0 - 0.5, t1: fig.t1, k };
  replay.cursor = replay.loop.t0;
  replay.lastNow = performance.now();
  clearTrail();
  replay.lastShown = k;
  if (k !== undefined) highlightRow(k);
  if (fig.grade) { showCoach(fig.grade); showGhost(fig, replay.samples); }
  setPlaying(true);
}
function showFigure(k) { const fig = replay.figures[k]; if (fig) loopFigure(fig, k); }
function gradeText(g) { return g ? `${g.type} ${g.hz ? 'HZ' : g.score.toFixed(1)} · ` : ''; }
// Coach: grade each figure the detector closes, show the card, and speak it when enabled.
const coachCard = document.getElementById('coachcard');
let coachShow = getItem('acroReplay.coachShow') !== 'off';   // the scoring box stays until the user toggles it off
let lastGrade = null;
let coachVoice = getItem('acroReplay.voice') || 'aircraft';
let coachSpeak = (getItem('acroReplay.speak') || 'on') === 'on';
let spinTurns = Number(getItem('acroReplay.spinTurns')) || 1.5;   // expected spin rotation, user-set; the Primary Known spin is fixed at 1.5
function coachContext() { return { axisDeg: boxGroup ? boxGroup.userData.headingDeg : NaN, spinTurns }; }
// Per-figure grading overrides the user sets in the replay Figures list (its expected type, its spin turns), so a
// maneuver is scored against what it was meant to be, not only what the detector guessed. Falls back to
// auto-detection and the global spin-turns default when the user has not overridden the figure.
function gradeOne(fig) {
  const ov = labels[labelKey(fig)] || {};
  const ctx = coachContext();
  if (Number.isFinite(ov.turns)) ctx.spinTurns = ov.turns;
  const want = PRIMARY.includes(ov.type) ? ov.type : undefined;
  return gradeFigure(fig, ctx, want);
}
function restoreLabels(name) {
  labels = {};
  try {
    const saved = JSON.parse(getItem(`acroReplay.labels.${name}`) || 'null');
    if (saved && Array.isArray(saved.figures)) {
      for (const f of saved.figures) labels[String(Math.round(f.t0))] = { type: f.type, grade: f.grade, notes: f.notes, turns: f.turns };
    }
  } catch (e) { /* ignore a malformed saved-labels blob */ }
}
function labelsBody() {
  return JSON.stringify({ flight: replay.name, figures: replay.figures.map((fig) => ({ t0: fig.t0, t1: fig.t1, elements: fig.elements.map(describe), ...(labels[labelKey(fig)] || {}) })) }, null, 1);
}
function persistLabels() { if (replay.name) setItem(`acroReplay.labels.${replay.name}`, labelsBody()); }
// The correct-figure ghost: white line for the ideal path, thin ribs from the flown path to it.
const ghostMat = new LineMaterial({ color: 0xffffff, linewidth: 4, worldUnits: false, transparent: true, opacity: 0.75 });
const ribMat = new LineMaterial({ color: 0xffffff, linewidth: 1.5, worldUnits: false, transparent: true, opacity: 0.35 });
let ghostLine = null, ribLines = null, ghostFor = null;
function clearGhost() {
  if (ghostLine) { scene.remove(ghostLine); ghostLine.geometry.dispose(); ghostLine = null; }
  if (ribLines) { scene.remove(ribLines); ribLines.geometry.dispose(); ribLines = null; }
  ghostFor = null;
}
function showGhost(fig, pool) {
  if (!fig.grade || !fig.grade.match) return;
  if (ghostFor === fig) return;
  clearGhost();
  const flown = pool.filter((s) => s.t >= fig.t0 && s.t <= fig.t1 && s.v);
  if (!flown.length) return;
  // The ideal aligns to the box, so pick the box axis from the settled direction of travel (the spin carries its
  // entry ground track), not the last entry sample, which is already swinging into the figure.
  const entryAz = Number.isFinite(fig.grade.measurements?.entryTrk) ? fig.grade.measurements.entryTrk
    : (fig.entry ? fig.entry.az1 : fig.elements[0].az0);
  const gctx = { ...(fig.grade.ctx || {}), axisDeg: coachContext().axisDeg };   // the live box edge, even if grading fell back off-axis
  const g = idealFigure(fig.grade, fig.grade.match, flown[0].v, entryAz, flown, gctx);
  if (!g) return;
  const geo = new LineGeometry();
  geo.setPositions(g.points.flatMap((p) => [p.x, p.y, p.z]));
  ghostLine = new Line2(geo, ghostMat); ghostLine.computeLineDistances(); ghostLine.frustumCulled = false;
  scene.add(ghostLine);
  if (g.ribs.length) {
    const rg = new LineSegmentsGeometry();
    rg.setPositions(g.ribs.flatMap(([a, b]) => [a.x, a.y, a.z, b.x, b.y, b.z]));
    ribLines = new LineSegments2(rg, ribMat); ribLines.frustumCulled = false;
    scene.add(ribLines);
  }
  ghostFor = fig;
}
// Coach mode: any Primary figure, one armed figure type, or the Primary Known flown in order.
let coachMode = getItem('acroReplay.coachFigure') || 'any';
const seq = { index: 0, scores: [] };
function seqLabel() { return coachMode === 'sequence' && seq.index < PRIMARY_KNOWN.length ? `${seq.index + 1}/${PRIMARY_KNOWN.length} · ` : ''; }
function resetSequence() { seq.index = 0; seq.scores = []; coachCard.classList.add('hidden'); }
function gradeForMode(fig) {
  if (coachMode === 'any') return gradeFigure(fig, coachContext());
  if (coachMode !== 'sequence') return matchFigure(fig, coachMode) ? gradeFigure(fig, coachContext(), coachMode) : null;
  const expected = PRIMARY_KNOWN[seq.index];
  if (!expected) return gradeFigure(fig, coachContext());
  const seqCtx = { ...coachContext(), ...(Number.isFinite(expected.turns) ? { spinTurns: expected.turns } : {}) };
  const g = matchFigure(fig, expected.type) ? gradeFigure(fig, seqCtx, expected.type) : null;
  if (g) {
    g.seq = { n: seq.index + 1, of: PRIMARY_KNOWN.length, k: expected.k };
    seq.scores.push({ type: g.type, score: g.hz ? 0 : g.score, k: expected.k });
    seq.index += 1;
    if (seq.index === PRIMARY_KNOWN.length) {
      const got = seq.scores.reduce((a, s) => a + s.score * s.k, 0), max = seq.scores.reduce((a, s) => a + 10 * s.k, 0);
      g.sequenceTotal = { got, max, pct: Math.round((got / max) * 100) };
      seq.index = 0; seq.scores = [];
    }
    return g;
  }
  const other = gradeFigure(fig, coachContext());
  if (other) other.unexpected = expected.type;
  return other;
}
function renderCoach(g) {
  const name = cap(g.type);
  const head = g.seq ? `${g.seq.n}/${g.seq.of} \u00b7 ${name} \u00b7 K${g.seq.k}` : name;
  const scoreTxt = g.hz ? 'HZ' : g.score.toFixed(1);
  let body;
  if (g.hz) {
    body = `<ul class="citems"><li><span class="cpts hz">HZ</span><span class="ctext">${g.hz}</span></li></ul>`;
  } else {
    const items = g.items.slice(0, 3).map((it) => {
      const pts = `\u2212${it.pts % 1 ? it.pts.toFixed(1) : it.pts}`;   // the score modifier (points off)
      const detail = it.detail ? `<span class="cdetail">${it.detail}</span>` : '';   // the measured rationale
      const fix = (coachVoice === 'control' && it.fix) ? `<span class="cfix">${it.fix}</span>` : '';
      return `<li><span class="cpts">${pts}</span><span class="ctext">${it.text}${detail}${fix}</span></li>`;
    });
    body = items.length ? `<ul class="citems">${items.join('')}</ul>` : '<p class="cok">Clean figure.</p>';
  }
  const warn = g.unexpected ? `<p class="cwarn">Expected ${g.unexpected} here \u2014 a hard zero in competition</p>` : '';
  const seq = g.sequenceTotal ? `<p class="cseq">Sequence ${Math.round(g.sequenceTotal.got)} / ${g.sequenceTotal.max} K \u00b7 ${g.sequenceTotal.pct}%</p>` : '';
  coachCard.innerHTML =
      `<div class="chead"><span class="ctype">${head}</span>`
    +   `<span class="cscorewrap"><span class="cscorelbl">auto</span><span class="cscore${g.hz ? ' hz' : ''}">${scoreTxt}</span></span></div>`
    + warn + body + seq;
}
// Show the scoring box for a figure. It stays up until the user toggles it off (no timeout, no tap-to-dismiss).
function showCoach(g) {
  lastGrade = g;
  if (!coachShow) return;
  renderCoach(g);
  coachCard.classList.remove('hidden');
}
function setCoachShow(on) {
  coachShow = on;
  setItem('acroReplay.coachShow', on ? 'on' : 'off');
  document.getElementById('coach-toggle').classList.toggle('on', on);
  if (on && lastGrade) { renderCoach(lastGrade); coachCard.classList.remove('hidden'); }
  else if (!on) coachCard.classList.add('hidden');
}
function say(text) { if (text && nativeHandler) nativeHandler.postMessage(`say:${text}`); else if (text && 'speechSynthesis' in window) { const u = new SpeechSynthesisUtterance(text); u.rate = 1.05; speechSynthesis.speak(u); } }
function onFigureDetected(fig, source) {
  fig.grade = gradeForMode(fig);
  let line = fig.grade ? critique(fig.grade, coachVoice, 3) : '';
  if (fig.grade?.seq) line = `Figure ${fig.grade.seq.n}. ${line}`;
  if (fig.grade?.unexpected) line = `Expected ${fig.grade.unexpected}. ${line}`;
  console.info(`[coach] figure (${source}) ${fmtClock(fig.dur)}: ${fig.elements.map(describe).join(' · ')}${line ? ` → ${line}` : ''}`);
  nativeLog(`figure ${fig.elements.map(describe).join(' | ')}${line ? ` → ${line}` : ''}`);
  if (fig.grade && source === 'live') {
    if (runState === 'recording') { runFigures.push(fig.grade); renderHudRec(); }
    showCoach(fig.grade);
    // The ideal-figure ghost is a review aid, not a live overlay — it only draws while scrubbing a replay.
    if (coachSpeak) say(line);
    if (runState === 'recording' && fig.grade.sequenceTotal) stopRun();   // sequence complete (last Known figure) -> end
  }
}

// Wing-rock run lifecycle. The pilot's entry rock starts recording a routine; the closing rock (or the next entry
// rock) ends it. The recording status rides at the bottom of the coach card, which stays where it is.
let runState = 'idle';        // 'idle' | 'recording' | 'done'
let runFigures = [];
let runDoneText = '';
let lastFlown = [];           // the last completed run's figures, for "draw my last flight as Aresti"
// The activated sequence's human name, so the pilot can verify the wing rock armed the one they meant to fly.
function seqName() {
  if (coachMode === 'sequence') return 'Primary Known';
  if (coachMode === 'any') return 'Freestyle';
  return cap(coachMode);
}
// Sequence score as a running K-weighted point total that starts at the perfect maximum and only falls as each
// figure's deductions land — shown as N/TOT so the pilot reads it like a competition score sheet. Only the ordered
// Known has a fixed maximum; free practice has no total.
function runTotal() {
  if (coachMode !== 'sequence') return null;
  const tot = PRIMARY_KNOWN.reduce((a, f) => a + 10 * f.k, 0);
  const lost = runFigures.reduce((a, g) => a + (g.hz ? 10 : 10 - g.score) * (g.seq?.k || 0), 0);
  return { n: Math.round(tot - lost), tot };
}
const hudRec = document.getElementById('hudrec');   // the recording strip lives on the always-visible HUD, not the
function renderHudRec() {                            // score card (which the pilot can toggle off)
  document.body.classList.toggle('seqactive', runState !== 'idle');   // the HUD grows a strip -> nudge the coach card down
  document.body.classList.toggle('recording', runState === 'recording');   // flips the Record button to its stop state
  if (runState === 'recording') {
    const total = runTotal();
    const last = runFigures[runFigures.length - 1];
    const prog = last && last.seq ? `${last.seq.n}/${last.seq.of}`
      : (runFigures.length ? `${runFigures.length} fig${runFigures.length === 1 ? '' : 's'}` : '');
    const bits = [seqName(), prog, total ? `${total.n}/${total.tot}` : ''].filter(Boolean);
    hudRec.className = 'rec';
    hudRec.innerHTML = `<span class="dot"></span>${bits.join(' \u00b7 ')}`;
  } else if (runState === 'done') {
    hudRec.className = 'done'; hudRec.textContent = runDoneText;
  } else {
    hudRec.className = 'hidden';
  }
  positionArestiOverlay();   // the HUD height just changed; keep the reference overlay clear of it
}
function resetRun() { runState = 'idle'; runFigures = []; renderHudRec(); }
// The run/record lifecycle is live-only: replaying a flight that happens to contain wing rocks must never start a
// recording, it is pure review. So the wing rock drives a run only when not replaying.
function onWingRock() { if (replay.active) return; if (runState === 'idle') startRun(); else stopRun(); }
function startRun() {
  runState = 'recording'; runFigures = []; resetSequence();
  if (nativeHandler && !replay.active) nativeHandler.postMessage(`seqstart:${seqName()}`);   // save this bracketed sequence as its own file, titled by the armed sequence (live only)
  renderHudRec();
  if (coachSpeak) say(`Recording ${seqName()}`);
}
function stopRun() {
  const total = runTotal();
  lastFlown = runFigures.slice();   // keep the flown figures for "draw my last flight as Aresti"
  if (lastFlown.length) document.getElementById('flown-draw').disabled = false;   // now there's a flight to draw
  runState = 'done';
  if (nativeHandler && !replay.active) nativeHandler.postMessage('seqend');
  runDoneText = total ? `${seqName()} saved \u00b7 ${total.n}/${total.tot}` : `${seqName()} saved`;
  renderHudRec();
  if (coachSpeak) say(total ? `${seqName()} complete. ${total.n} of ${total.tot}.` : `${seqName()} saved.`);
  setTimeout(() => { if (runState === 'done') { runState = 'idle'; renderHudRec(); } }, 6000);
}
// The Sequences view: one "Loaded sequence" menu drives both live coaching and the reference Aresti. Freestyle and
// single figures coach directly; the IAC Knowns and a Custom build load a reference drawing (vendored OpenAero).
const seqSelect = document.getElementById('coach-figure');
const knownGroup = document.getElementById('known-group');
POWER_KNOWNS_2026.forEach((s) => {
  const o = document.createElement('option');
  o.value = s.key;                                          // e.g. "2026 IAC Primary Known" (year already in the name)
  o.textContent = `${s.key.replace('IAC ', '')} · K${s.k}`;   // -> "2026 Primary Known · K58"
  knownGroup.appendChild(o);
});
const arestiView = document.getElementById('aresti-view');
const arestiExport = document.getElementById('aresti-export');
const arestiToggle = document.getElementById('aresti-toggle');
const arestiOverlay = document.getElementById('aresti-overlay');
const arestiOverlayBody = document.getElementById('aresti-overlay-body');
let activeAresti = null;   // { svg, title } — the current drawing, available to export and to show on screen
function showAresti(res, title) {
  if (!res || !res.valid) { arestiView.innerHTML = `<div class="amsg">${res && res.error ? 'Could not draw that sequence.' : 'No figures recognised — check the notation.'}</div>`; arestiExport.disabled = true; return; }
  arestiView.innerHTML = `<div class="ahead">${title} · K ${res.k} · ${res.figures.length} figure${res.figures.length === 1 ? '' : 's'}</div>${res.svg}`;
  activeAresti = { svg: res.svg, title: `${title} · K ${res.k}` };
  arestiExport.disabled = false;   // there's a drawing to export now
  arestiToggle.classList.remove('pending');   // a sequence exists -> the on-screen toggle is now usable (grey, not dimmed)
}
function clearAresti() { arestiView.innerHTML = ''; activeAresti = null; arestiExport.disabled = true; arestiToggle.classList.add('pending'); }

// Single figures the coach grades one-off, mapped to an OLAN token so the menu can also draw them as a reference.
const FIGURE_OLAN = { '45 up line': 'd', spin: '1s', 'half cuban': 'c', loop: 'o', '180 turn': '2j', 'slow roll': '1' };
const KNOWN_KEYS = new Set(POWER_KNOWNS_2026.map((s) => s.key));
const customBuilder = document.getElementById('custom-builder');
// Apply a "Loaded sequence" selection: set the coach grading mode and (optionally) draw its reference Aresti.
async function applyLoadedSeq(value, draw) {
  setItem('acroReplay.loadedSeq', value);
  customBuilder.classList.toggle('hidden', value !== 'custom');
  if (value === 'custom') { coachMode = 'any'; setItem('acroReplay.coachFigure', 'any'); resetSequence(); syncSpinField(); return; }
  const known = KNOWN_KEYS.has(value);
  coachMode = known ? (value === '2026 IAC Primary Known' ? 'sequence' : 'any') : value;   // only Primary is graded as a sequence
  setItem('acroReplay.coachFigure', coachMode);
  resetSequence(); syncSpinField();
  if (!draw) return;
  if (known) { arestiView.innerHTML = '<div class="amsg">Drawing…</div>'; showAresti(await renderLibrary(value), value.replace('IAC ', '')); }
  else if (FIGURE_OLAN[value]) { arestiView.innerHTML = '<div class="amsg">Drawing…</div>'; showAresti(await renderSequence(FIGURE_OLAN[value]), cap(value)); }
  else clearAresti();   // Freestyle: nothing to reference
}
seqSelect.addEventListener('change', (e) => applyLoadedSeq(e.target.value, true));
// Restore the saved selection, defaulting to the Primary Known (migrating the old "sequence" value to its key).
let savedSeq = getItem('acroReplay.loadedSeq') || getItem('acroReplay.coachFigure') || '2026 IAC Primary Known';
if (savedSeq === 'sequence') savedSeq = '2026 IAC Primary Known';
if (![...seqSelect.options].some((o) => o.value === savedSeq)) savedSeq = '2026 IAC Primary Known';
seqSelect.value = savedSeq;
applyLoadedSeq(savedSeq, true);   // draw the reference Aresti on boot so it's ready to view/overlay

// Custom builder: tap figures to queue them in order, then draw the set as one Aresti sequence.
const CUSTOM_FIGURES = [
  ['Loop', 'o'], ['Half Cuban', 'c'], ['Immelmann', 'm'], ['Split-S', 'a'],
  ['Hammerhead', 'h'], ['Humpty', 'b'], ['45° up', 'd'], ['45° down', 'id'],
  ['Turn 180°', '2j'], ['Roll', '1'], ['Spin', '1s'], ['Snap', '1f'],
];
const customList = document.getElementById('custom-list');
let customPicks = [];
function renderCustomList() {
  customList.innerHTML = customPicks.length
    ? customPicks.map((p, i) => `<span class="chip">${i + 1}. ${p.name}</span>`).join('')
    : '<span class="amsg">No figures yet</span>';
}
const customPalette = document.getElementById('custom-palette');
CUSTOM_FIGURES.forEach(([name, olan]) => {
  const b = document.createElement('button');
  b.className = 'secondary small';
  b.textContent = name;
  b.addEventListener('click', () => { customPicks.push({ name, olan }); renderCustomList(); });
  customPalette.appendChild(b);
});
renderCustomList();
document.getElementById('custom-undo').addEventListener('click', () => { customPicks.pop(); renderCustomList(); });
document.getElementById('custom-clear').addEventListener('click', () => { customPicks = []; renderCustomList(); });
document.getElementById('custom-draw').addEventListener('click', async () => {
  if (!customPicks.length) { arestiView.innerHTML = '<div class="amsg">Add some figures first.</div>'; return; }
  arestiView.innerHTML = '<div class="amsg">Drawing…</div>';
  showAresti(await renderSequence(customPicks.map((p) => p.olan).join(' ')), 'Custom');
});
document.getElementById('olan-draw').addEventListener('click', async () => {
  const olan = document.getElementById('olan-import').value.trim();
  if (!olan) return;
  arestiView.innerHTML = '<div class="amsg">Drawing…</div>';
  showAresti(await renderSequence(olan), 'Imported');
});
document.getElementById('flown-draw').addEventListener('click', async () => {
  if (!lastFlown.length) { arestiView.innerHTML = '<div class="amsg">No flight recorded yet — fly a sequence first.</div>'; return; }
  const tokens = flownToOlan(lastFlown).split(' ').filter(Boolean);   // one figure per token -> drawn as a spaced grid
  if (!tokens.length) { arestiView.innerHTML = '<div class="amsg">No figures were recognised in the last flight.</div>'; return; }
  arestiView.innerHTML = '<div class="amsg">Drawing…</div>';
  showAresti(await renderFigureGrid(tokens), 'My last flight');
});
// Export the drawn sequence as a PNG — native share sheet on the phone, file download in the browser.
function svgToPng(svg, targetW = 1600) {
  return new Promise((resolve, reject) => {
    const vb = (svg.match(/viewBox="([^"]+)"/) || [])[1] || '0 0 100 100';
    const p = vb.split(/\s+/).map(Number); const aspect = (p[2] || 1) / (p[3] || 1);
    const W = targetW; const H = Math.max(1, Math.round(targetW / aspect));
    const sized = /<svg[^>]*\swidth=/.test(svg) ? svg : svg.replace('<svg', `<svg width="${W}" height="${H}"`);
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas'); c.width = W; c.height = H;
      const ctx = c.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H); ctx.drawImage(img, 0, 0, W, H);
      resolve(c.toDataURL('image/png'));
    };
    img.onerror = reject;
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(sized);
  });
}
document.getElementById('aresti-export').addEventListener('click', async () => {
  if (!activeAresti) return;
  const name = `${(activeAresti.title || 'sequence').replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '')}.png`;
  try {
    const png = await svgToPng(activeAresti.svg);
    if (nativeHandler) nativeHandler.postMessage(`export:${name}:${png.split(',')[1]}`);   // Swift presents a share sheet
    else { const a = document.createElement('a'); a.href = png; a.download = name; document.body.appendChild(a); a.click(); a.remove(); }
  } catch (e) { nativeLog(`export failed: ${e.message || e}`); }
});
// On-screen reference overlay: show the active sequence beside the live view (half screen on a tablet, corner on a phone).
// Sit the overlay just under the HUD's actual bottom (which grows with the recording strip and can wrap on a phone),
// so it never overlaps regardless of device or HUD state.
function positionArestiOverlay() {
  const hud = document.getElementById('hud');
  const ov = document.getElementById('aresti-overlay');   // by id (not the const) so an early renderHudRec can't hit the TDZ
  if (hud && ov && !ov.classList.contains('hidden')) ov.style.top = `${Math.round(hud.getBoundingClientRect().bottom) + 10}px`;
}
// With the reference sequence up (centred at the top), drop the aircraft into the lower part of the frame so it
// reads as sitting below the Aresti. A negative Y view-offset shifts the rendered scene down; cleared when hidden.
const ARESTI_VIEW_DROP = 0.2;
function applyArestiViewShift() {
  const w = window.innerWidth, h = window.innerHeight;
  if (arestiOverlay.classList.contains('hidden')) camera.clearViewOffset();
  else camera.setViewOffset(w, h, 0, -Math.round(h * ARESTI_VIEW_DROP), w, h);
}
function openArestiOverlay() { if (!activeAresti) return; arestiOverlayBody.innerHTML = activeAresti.svg; arestiOverlay.classList.remove('hidden'); arestiToggle.classList.add('on'); positionArestiOverlay(); applyArestiViewShift(); }
function closeArestiOverlay() { arestiOverlay.classList.add('hidden'); arestiToggle.classList.remove('on'); applyArestiViewShift(); }
arestiToggle.addEventListener('click', () => {
  if (!activeAresti) return;   // nothing drawn yet (button is dimmed)
  if (arestiOverlay.classList.contains('hidden')) openArestiOverlay();
  else closeArestiOverlay();
});
const spinTurnsInput = document.getElementById('spin-turns');
spinTurnsInput.value = spinTurns;
spinTurnsInput.addEventListener('change', (e) => {
  const v = Math.max(0.25, Math.round(Number(e.target.value) * 4) / 4) || 1.5;   // quarter-turn granularity
  spinTurns = v; e.target.value = v; setItem('acroReplay.spinTurns', String(v)); regradeReplay();
});
// Spin turns only bites when the coached figure is a spin (in a sequence the count is fixed) — hide it otherwise.
function syncSpinField() { document.getElementById('spin-turns-field').classList.toggle('hidden', coachMode !== 'spin'); }
syncSpinField();
const trailSecsInput = document.getElementById('trail-secs');
const trailSecsVal = document.getElementById('trail-secs-val');
trailSecsInput.value = trailSeconds;
trailSecsVal.textContent = `${trailSeconds} s`;
trailSecsInput.addEventListener('input', (e) => { setTrailSeconds(Number(e.target.value)); trailSecsVal.textContent = `${trailSeconds} s`; });
const axesToggle = document.getElementById('axes-toggle');
axesToggle.classList.toggle('on', axesOn);
axesToggle.addEventListener('click', () => {
  axesOn = !axesOn;
  setItem('acroReplay.axes', axesOn ? 'on' : 'off');
  axesToggle.classList.toggle('on', axesOn);
  bodyAxes.visible = axesOn && !hangarMode;   // box axes follow in the frame loop
});
document.getElementById('coach-toggle').classList.toggle('on', coachShow);
document.getElementById('coach-toggle').addEventListener('click', () => setCoachShow(!coachShow));
document.querySelectorAll('#voice [data-voice]').forEach((btn) => {
  btn.classList.toggle('on', btn.dataset.voice === coachVoice);
  btn.addEventListener('click', () => { coachVoice = btn.dataset.voice; setItem('acroReplay.voice', coachVoice); document.querySelectorAll('#voice [data-voice]').forEach((b) => b.classList.toggle('on', b === btn)); });
});
document.querySelectorAll('#speak [data-speak]').forEach((btn) => {
  btn.classList.toggle('on', (btn.dataset.speak === 'on') === coachSpeak);
  btn.addEventListener('click', () => { coachSpeak = btn.dataset.speak === 'on'; setItem('acroReplay.speak', coachSpeak ? 'on' : 'off'); document.querySelectorAll('#speak [data-speak]').forEach((b) => b.classList.toggle('on', b === btn)); });
});

// Live guidance tone (in-figure feedback by ear). Settings pick the mode and volume; the audio engine only wakes
// on a user gesture (a mode tap or Test), which iOS requires. Live per-figure driving is wired via liveCue.update().
const liveCue = new LiveCue();
const cueMapper = new LiveCueMap();
let cueMode = getItem('acroReplay.liveCue') || 'off';
let cueVol = Number(getItem('acroReplay.cueVol'));
if (!Number.isFinite(cueVol)) cueVol = 70;
liveCue.mode = cueMode; liveCue.setVolume(cueVol / 100);
document.querySelectorAll('#livecue [data-cue]').forEach((btn) => {
  btn.classList.toggle('on', btn.dataset.cue === cueMode);
  btn.addEventListener('click', () => {
    cueMode = btn.dataset.cue; setItem('acroReplay.liveCue', cueMode);
    document.querySelectorAll('#livecue [data-cue]').forEach((b) => b.classList.toggle('on', b === btn));
    liveCue.setMode(cueMode);
  });
});
const cueVolEl = document.getElementById('cue-vol');
cueVolEl.value = cueVol;
cueVolEl.addEventListener('input', () => { cueVol = Number(cueVolEl.value); setItem('acroReplay.cueVol', String(cueVol)); liveCue.setVolume(cueVol / 100); });
document.getElementById('cue-test').addEventListener('click', () => liveCue.test());
rb['rb-play'].addEventListener('click', () => setPlaying(!replay.playing));
rb['rb-scrub'].addEventListener('input', () => { setPlaying(false); replay.loop = null; seekTo(replay.t0 + (rb['rb-scrub'].value / 1000) * (replay.t1 - replay.t0)); });
rb['rb-speed'].addEventListener('click', () => { const seq = [0.25, 0.5, 1, 2, 4, 8]; replay.speed = seq[(seq.indexOf(replay.speed) + 1) % seq.length]; rb['rb-speed'].textContent = `${replay.speed}×`; });
rb['rb-toggle-list'].addEventListener('click', () => rb['rb-list'].classList.toggle('hidden'));
rb['rb-last'].addEventListener('click', () => {
  const figs = liveDetector.figures;
  if (!figs.length) { rb['rb-time'].textContent = 'no figure yet'; return; }
  const fig = figs[figs.length - 1];
  const slice = history.filter((s) => s.t >= fig.t0 - 4 && s.t <= fig.t1 + 4);
  startReplay(slice, 'last figure', fig.t0 - 0.5, [fig]);   // keep the live detection and its grade
  loopFigure(fig, 0);   // loop just this figure with its own trail
});
rb['rb-load'].addEventListener('click', async () => {
  const name = rb['rb-flight'].value;
  if (!name) return;
  rb['rb-time'].textContent = 'loading…';
  try { const { samples, box: flightBox, meta } = await loadFlight(`/flights/${encodeURIComponent(name)}`); if (meta && meta.model && MODELS[meta.model] && meta.model !== modelKey) setModel(meta.model); startReplay(samples, name, undefined, undefined, flightBox); }
  catch (e) { rb['rb-time'].textContent = String(e.message || e); }
});
document.getElementById('rb-sim').addEventListener('click', () => { if (sim) stopSim(); else startSim(rb['rb-flight'].value); });
rb['rb-save'].addEventListener('click', async () => {
  const body = labelsBody();
  persistLabels();
  if (!nativeHandler) {
    const r = await fetch(`/dev/labels/${encodeURIComponent(replay.name.replace(/\.bin$/, ''))}`, { method: 'POST', body });
    rb['rb-time'].textContent = r.ok ? 'labels saved' : `save failed ${r.status}`;
  } else rb['rb-time'].textContent = 'labels saved';
});
document.getElementById('replay-toggle').addEventListener('click', () => {
  if (replay.active) { stopReplay(); return; }          // playing a flight -> go live
  const nowHidden = rb.replaybar.classList.toggle('hidden');
  document.body.classList.toggle('replaying', !nowHidden);
  if (!nowHidden) listFlights();
  setReplayLabel();
});
function showFlights(files) {
  rb['rb-flight'].innerHTML = files.map((f) => `<option value="${f.name}">${f.name} (${(f.bytes / 1e6).toFixed(1)} MB)</option>`).join('');
  const want = params.get('flight');
  if (want && files.some((f) => f.name === want)) { rb['rb-flight'].value = want; rb['rb-load'].click(); }
}
async function listFlights() {
  if (nativeHandler) { nativeHandler.postMessage('flights'); return; }   // answered via acroReplay.flights()
  try { showFlights(await (await fetch('/flights/')).json()); } catch (e) { /* no bridge: nothing to list */ }
}
listFlights();

// Cameras. Orbit: OrbitControls around the aircraft (pinch/wheel zooms). Chase: rigidly attached to the
// airframe — it rolls and pitches with the aircraft. Judge: fixed at the box's judging position.
let camMode = 'orbit';
let prevCamMode = 'orbit';
// Map picking looks straight down from `height`; it can pull back far enough to see a whole region, which
// needs the fog off and a deep clip range (both restored when the map closes).
const MAP_HEIGHT = { start: 2500, min: 150, max: 150000 };
const MAP_CLIP = { near: 5, far: 1.2e6 };
const mapCam = { height: MAP_HEIGHT.start };
let pickState = null;
let pickBoxCenter = null;   // world position of the last-tapped box centre, for its map marker
const pickMarkers = new THREE.Group();
scene.add(pickMarkers);
const camOffset = new THREE.Vector3(14, 11, 52);   // used to seat the Free view when entering it
// Orbit is a detached, heading-aligned chase: it sits behind the aircraft along its (smoothed) direction of travel,
// stays world-upright, and eases rather than snapping — so you look down the flight line and can read a vertical's
// left/right lean. It holds the last heading through verticals, where horizontal travel vanishes. Pinch to zoom.
const orbitDir = new THREE.Vector3(0, 0, 1);   // smoothed horizontal travel direction the camera sits behind
const orbitPrev = new THREE.Vector3();
let orbitDist = 55;
const ORBIT_HEIGHT = 11;
const _ovel = new THREE.Vector3(), _odir = new THREE.Vector3();
function updateOrbitChase(p) {
  if (controls.enabled) controls.enabled = false;   // orbit drives itself in flight (hangar re-enables OrbitControls)
  _ovel.copy(p).sub(orbitPrev); orbitPrev.copy(p);
  _odir.set(_ovel.x, 0, _ovel.z);
  if (_odir.lengthSq() > 0.02) {          // moving horizontally -> ease the follow heading toward the travel direction
    _odir.normalize();
    orbitDir.lerp(_odir, 0.05);
    if (orbitDir.lengthSq() > 1e-6) orbitDir.normalize(); else orbitDir.set(0, 0, 1);
  }
  camera.up.set(0, 1, 0);
  camera.position.copy(p).addScaledVector(orbitDir, -orbitDist);
  camera.position.y += ORBIT_HEIGHT;
  camera.lookAt(p);
}
const chase = { dist: 32 };
const judge = { fov: 22, zoom: 1 };   // auto FOV keeps the aircraft a constant size; ± scales it
const DEFAULT_FOV = 55;
const bodyUp = new THREE.Vector3();
const chaseOff = new THREE.Vector3();
// Orbit pan (replay only): a world-space offset the user drags the follow point by, on top of the aircraft.
const orbitPan = new THREE.Vector3();
const lastOrbitTarget = new THREE.Vector3();
const camTmp = new THREE.Vector3();
function setCamMode(mode) {
  const prev = camMode;
  camMode = mode;
  document.querySelectorAll('#controls [data-cam]').forEach(b => b.classList.toggle('on', b.dataset.cam === mode));
  applyScene();
  if (hangarMode) { hangarControls(); return; }   // in the hangar every mode orbits; the choice applies once airborne
  const mapMode = mode === 'map';
  controls.minDistance = mapMode ? MAP_HEIGHT.min : 4;
  controls.maxDistance = mapMode ? MAP_HEIGHT.max : 3000;
  camera.near = mapMode ? MAP_CLIP.near : FLIGHT_CLIP.near;
  camera.far = mapMode ? MAP_CLIP.far : FLIGHT_CLIP.far;
  scene.fog.near = mapMode ? 1e7 : FOG.near;
  scene.fog.far = mapMode ? 2e7 : FOG.far;
  camera.updateProjectionMatrix();
  const panning = mode === 'free';   // Free is the only user-orbited flight view; Orbit now drives itself
  controls.enabled = mode === 'map' || mode === 'free';
  controls.enableRotate = mode !== 'map';
  controls.enablePan = mode === 'map' || panning;
  controls.screenSpacePanning = true;
  // Map mode: one finger pans. Orbit: one finger rotates; two fingers pan (in replay) or dolly.
  controls.mouseButtons.LEFT = mode === 'map' ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
  controls.touches.ONE = mode === 'map' ? THREE.TOUCH.PAN : THREE.TOUCH.ROTATE;
  // Orbit follows the aircraft: two fingers dolly + rotate but never pan, so a pinch-zoom can't drift the target
  // off the aircraft and flip to Free. Free and Map are the pan-around views, so they keep dolly-pan.
  controls.touches.TWO = (mode === 'map' || mode === 'free') ? THREE.TOUCH.DOLLY_PAN : THREE.TOUCH.DOLLY_ROTATE;
  controls.panSpeed = mode === 'map' ? 1.6 : 1;
  controls.maxPolarAngle = mode === 'map' ? 0.001 : Math.PI;
  camera.up.set(0, 1, 0);
  if (mode !== 'judge') { camera.fov = DEFAULT_FOV; camera.updateProjectionMatrix(); }
  if (mode === 'orbit') {   // seed the chase heading from the aircraft's current facing so it starts aligned behind
    orbitPrev.copy(aircraft.position);
    _odir.set(1, 0, 0).applyQuaternion(aircraft.quaternion); _odir.y = 0;
    if (_odir.lengthSq() > 0.02) orbitDir.copy(_odir.normalize());
  }
  if (mode === 'free' && prev !== 'free') { controls.target.copy(aircraft.position); camera.position.copy(aircraft.position).add(camOffset); controls.update(); }
  if (mode === 'map') {
    const c = boxGroup ? judgeWorldPosition(boxGroup, new THREE.Vector3()) : aircraft.position.clone();
    controls.target.set(c.x, 0, c.z);
    camera.position.set(c.x, mapCam.height, c.z + 0.01);
    controls.update();
  }
}
function zoomBy(f) {
  if (camMode === 'orbit' && !hangarMode) {
    orbitDist = THREE.MathUtils.clamp(orbitDist * f, 15, 400);   // the self-driving chase owns its own distance
  } else if (hangarMode || camMode === 'free') {
    const d = camera.position.clone().sub(controls.target);
    const len = THREE.MathUtils.clamp(d.length() * f, controls.minDistance, controls.maxDistance);
    camera.position.copy(controls.target).add(d.setLength(len));
  } else if (camMode === 'chase') {
    chase.dist = THREE.MathUtils.clamp(chase.dist * f, 5, 300);
  } else if (camMode === 'judge') {
    judge.zoom = THREE.MathUtils.clamp(judge.zoom * f, 0.1, 80);
  } else if (camMode === 'map') {
    mapCam.height = THREE.MathUtils.clamp(mapCam.height * f * f, MAP_HEIGHT.min, MAP_HEIGHT.max);   // buttons take bigger steps on the map
    camera.position.set(controls.target.x, mapCam.height, controls.target.z + 0.01);
    controls.update();
  }
}
document.querySelectorAll('#controls [data-cam]').forEach(b => b.addEventListener('click', () => setCamMode(b.dataset.cam)));
document.getElementById('record-toggle').addEventListener('click', () => { if (!replay.active) onWingRock(); });   // manual start/stop, same toggle as the wing rock
document.getElementById('clear').addEventListener('click', clearTrail);
document.getElementById('zoom-in').addEventListener('click', () => zoomBy(0.75));
document.getElementById('zoom-out').addEventListener('click', () => zoomBy(1.33));
canvas.addEventListener('wheel', (e) => { if (!controls.enabled) { e.preventDefault(); zoomBy(Math.exp(e.deltaY * 0.0015)); } }, { passive: false });   // OrbitControls dollies the enabled views; self-driving views zoom manually
let pinchDist = 0;
canvas.addEventListener('touchstart', (e) => { if (e.touches.length === 2) pinchDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); }, { passive: true });
canvas.addEventListener('touchmove', (e) => {
  if (controls.enabled || e.touches.length !== 2) return;   // OrbitControls handles pinch for the enabled views
  const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
  if (pinchDist > 0) zoomBy(pinchDist / d);
  pinchDist = d;
}, { passive: true });

function updateCamera() {
  const p = aircraft.position;
  if (boxGroup) boxGroup.userData.judgeMarker.visible = camMode !== 'judge';   // the marker would fill the judge's view
  if (hangarMode) {                               // parked: orbit the plane at rest with OrbitControls
    camTmp.copy(p).add(orbitPan);
    camera.position.add(camTmp).sub(controls.target);
    controls.target.copy(camTmp);
    lastOrbitTarget.copy(camTmp);
    controls.update();
  } else if (camMode === 'orbit') {
    updateOrbitChase(p);                          // detached, heading-aligned chase behind the flight line
  } else if (camMode === 'free') {
    controls.update();                            // world-fixed: the aircraft flies through, the view stays put
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
  const s = replay.active ? replay.current : latest;
  const fresh = replay.active ? !!s : (!!s && socketOpen && now - lastRecv <= STALE_MS);
  const gps = phoneFix ? ` · phone GPS ±${units.fmtLen(phoneFix.acc)}` : '';
  let text, cls;
  if (replay.active) { text = `replay · ${replay.name}`; cls = ''; }
  else if (!socketOpen) { text = `no Hub${gps}`; cls = 'bad'; }
  else if (!fresh) { text = `no data${gps}`; cls = 'bad'; }
  else if (!s.init) { text = `INS init · ${s.sats} sats`; cls = ''; }
  else if (!s.ok) { text = `INS degraded · ${s.sats} sats`; cls = ''; }
  else { text = `${s.sats} sats · ±${units.fmtLen(s.hacc * units.FT_TO_M)}`; cls = 'good'; }
  status.firstElementChild.textContent = text;
  status.className = `badge ${cls}`;
  document.body.classList.toggle('live', fresh && !replay.active);   // gates the Record button: only offer it with a live feed
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
    flights: showFlights,
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
  ghostMat.resolution.set(w, h);
  ribMat.resolution.set(w, h);
  applyArestiViewShift();   // recompute the view-offset against the new size (or leave it cleared)
}
window.addEventListener('resize', resize);
resize();
setCamMode('orbit');
applyScene();

let booted = false;
const SPLASH_MIN_MS = 3000;                 // hold the logo splash at least this long, even on a fast launch
const splashT0 = performance.now();
function dismissSplash() {
  const el = document.getElementById('splash');
  if (!el) return;
  const wait = Math.max(0, SPLASH_MIN_MS - (performance.now() - splashT0));
  setTimeout(() => { el.classList.add('gone'); setTimeout(() => el.remove(), 600); }, wait);
}
// Live guidance tone: each frame, read the detector's in-progress element and feed the tone engine the current
// deviation. Silent unless the cue is on, a fresh feed is arriving live (not replay), and we're on a cue-able
// element; feeding update(0, 0) parks the tone inside its deadband so a stalled feed can't leave it hanging.
let lastCue = { active: false, shape: 0, bank: 0 };
function updateCue(now) {
  if (liveCue.testing) return;   // a Test sample is playing — don't overwrite it with the live drive
  const live = !replay.active && now - lastRecv <= STALE_MS && !!liveDetector.lastF;
  // Drive the mapper every frame (advancing loop-radius capture) but feed the engine only with a live figure;
  // drive(null, null) resets per-element state when the feed drops so the next element re-captures cleanly.
  lastCue = live ? cueMapper.drive(liveDetector.current, liveDetector.lastF) : cueMapper.drive(null, null);
  if (cueMode !== 'off') liveCue.update(lastCue.active ? lastCue.shape : 0, lastCue.active ? lastCue.bank : 0);
}
function frame() {
  const now = performance.now();
  let pose;
  if (replay.active) {
    pose = replayTick(now);
  } else {
    if (sim) simFeed(now);
    const flying = (socketOpen || sim) && latest && latest.init && now - lastRecv < REST_AFTER_MS;
    pose = flying ? poseAt(now - RENDER_DELAY_MS) : null;
  }
  if (pose) {
    if (parked) { parked = false; applyScene(); }
    aircraft.position.copy(pose.v);
    aircraft.quaternion.copy(pose.q);
    if (replay.active ? replay.playing : now - lastRecv < STALE_MS) pushTrail(pose.v, now);
  } else if (!parked) {
    parked = true;
    samples.length = 0;
    placeParked();
    applyScene();
  }
  updateCamera();
  // Box-aligned grey lines: centred on the aircraft, held in the box orientation (needs a box; flight only).
  boxAxes.visible = axesOn && !hangarMode && !!boxGroup;
  if (boxAxes.visible) { boxAxes.position.copy(aircraft.position); boxAxes.quaternion.copy(boxGroup.quaternion); }
  updateHud(now);
  updateCue(now);
  renderer.render(scene, camera);
  trailFullUpload = false;
  if (!booted) { booted = true; dismissSplash(); }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
// Debug hook for the browser console / simulator log.
window.wingrock = {
  trail: () => ({ len: trailLen, instances: trailGeo.instanceCount, visible: trail.visible, lastMs: trailLastMs, full: trailFullUpload, ranges: seg.updateRanges && seg.updateRanges.length }),
  replay: () => ({ active: replay.active, playing: replay.playing, cursor: replay.cursor, n: replay.samples.length, figures: replay.figures.length, parked, hangarMode }),
  ghost: () => ({ for: ghostFor && Math.round(ghostFor.t0 - replay.t0), points: ghostLine ? ghostLine.geometry.attributes.instanceStart.count : 0, ribs: ribLines ? ribLines.geometry.attributes.instanceStart.count : 0 }),
  rocks: async (name) => {
    const { samples } = await loadFlight(`/flights/${encodeURIComponent(name || replay.name)}`);
    const found = []; const d = new WingRockDetector((r) => found.push({ t: Math.round(r.t - samples[0].t), dir: r.dir }));
    for (const smp of samples) if (smp.init) d.push(smp);
    return found;
  },
  run: () => ({ runState, runFigures: runFigures.length, cursor: Math.round(replay.cursor - replay.t0), fig0: replay.figures[0] ? Math.round(replay.figures[0].t0 - replay.t0) : null }),
  grades: () => replay.figures.filter((f) => f.grade).map((f) => ({ t: Math.round(f.t0 - replay.t0), type: f.grade.type, score: f.grade.score, hz: f.grade.hz, items: f.grade.items.map((i) => `${i.pts} ${i.text} (${i.detail || ''})`), m: f.grade.measurements })),
  cue: () => { const f = liveDetector.lastF; return { mode: cueMode, kind: liveDetector.current?.kind, el: f && Math.round(f.el), roll: f && Math.round(f.roll), active: lastCue.active, shape: Math.round(lastCue.shape), bank: Math.round(lastCue.bank) }; },
  cueEngine: () => ({ mode: liveCue.mode, testing: liveCue.testing, ctx: liveCue.ctx?.state || null, envGain: liveCue.env ? +liveCue.env.gain.value.toFixed(3) : null, freq: liveCue.osc ? Math.round(liveCue.osc.frequency.value) : null }),
  cam: () => ({ mode: camMode, parked, hangarMode, orbitPanSq: +orbitPan.lengthSq().toFixed(1) }),
};
