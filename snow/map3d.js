// 3D map of one region: real terrain, resorts and peaks as snow stakes for the current storm, live road status,
// and the avalanche danger rating as an optional tint.
// Scene units are kilometers; x is east, y is north, z is up.
import * as THREE from "three";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";

const EXAGGERATION = 2.7;
const STAKE_KM_PER_IN = 0.16;
const STAKE_RADIUS = 0.7;
const FLAKES = 9000;
const WHITEN_AT_IN = 5;
const BIN_M = 50;
// The snow already lying whitens the land too, but more slowly than fresh snow does: this much of it is full white.
const PACK_WHITE_IN = 12;
const FLOOR_M = 1150;
const LOWLAND_M = 400;
const EDGE_FADE_KM = 16;
const GLOBE_KM = 50;
const DISC_KM = 72;
const DISC_FADE_KM = 10;
const SKY_KM = 110;
const DOME_SQUASH = 0.62;
const DRY_GAP_H = 24;
const DRY_RATE = 0.01;
const MAX_AHEAD_H = 96;
const ROAD_LIFT = 0.16;
const ROAD_COLORS = {open: [0.20, 0.23, 0.27], chains: [0.96, 0.66, 0.05], closed: [0.84, 0.18, 0.18]};
const MAJOR = new Set(["I-80", "US-50", "US-395", "I-580"]);
const DANGER_TINT = 0.55;
const SHIELD_EVERY_KM = 26;

// Interstate, U.S. route, California state route (the green spade), and Nevada state route (the state outline) markers.
const SHIELD_FONT = "system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif";
const INTERSTATE = "M80.8 0C115.4 10.6 152.2 16.3 190.4 16.3S265.3 10.6 300 0C334.7 10.6 371.5 16.3 409.6 16.3S484.6 10.6 519.2 0"
  + "C569.8 63.9 600 144.7 600 232.5C600 413.9 471.2 565.3 300 600C128.8 565.3 0 413.9 0 232.5C0 144.7 30.2 63.9 80.8 0z";
const INTERSTATE_TOP = "M80.8 0C115.4 10.6 152.2 16.3 190.4 16.3S265.3 10.6 300 0C334.7 10.6 371.5 16.3 409.6 16.3S484.6 10.6 519.2 0"
  + "C546.8 34.8 568.3 74.6 582.2 118H17.8C31.7 74.6 53.2 34.8 80.8 0z";
const US_ROUTE = "M300 10c23.6 20.1 54.1 32.2 87.5 32.2S451.4 30.1 475 10l115 115c-21.2 30.1-33.6 66.8-33.6 106.3"
  + "c0 28.5 6.4 55.4 17.9 79.5C584.2 331.7 590 355.4 590 380c0 88.4-71.6 160-160 160h-25.1c-42.3 0-80.1 19.5-104.9 50"
  + "c-24.8-30.5-62.5-50-104.9-50H170C81.6 540 10 468.4 10 380c0-24.6 5.8-48.3 15.7-69.2C37.2 286.7 43.6 259.8 43.6 231.3"
  + "C43.6 191.8 31.2 155.1 10 125L125 10c23.6 20.1 54.1 32.2 87.5 32.2S276.4 30.1 300 10z";
const CA_SPADE = "M0.5 262C0.5 139.3 81.2 35.4 192.5 0.5C303.8 35.4 384.5 139.3 384.5 262v63.6c0 30-21.3 55-49.6 60.8"
  + "C288.4 395.7 241 400.5 192.5 400.5S96.6 395.7 50.1 386.4C21.8 380.7 0.5 355.7 0.5 325.7z";
const NEVADA = "M100 50H500V478L470 499L481 543L498 569L100 318z";

function shieldSVG(route) {
  const [kind, number] = route.split("-"), long = number.length > 2;
  const text = (fill, x, y, size) => `<text x="${x}" y="${y}" text-anchor="middle" font-size="${size}" font-weight="700" font-family="${SHIELD_FONT}" fill="${fill}">${number}</text>`;
  const wrap = (box, inner) => `<svg viewBox="${box}" width="26" height="26" aria-hidden="true">${inner}</svg>`;
  if (kind === "I") {
    return wrap("-10 -10 620 620", `<path d="${INTERSTATE}" fill="#fff"/>
      <g transform="translate(300 290) scale(.93) translate(-300 -290)"><path d="${INTERSTATE}" fill="#003f87"/>
      <rect y="118" width="600" height="32" fill="#fff"/><path d="${INTERSTATE_TOP}" fill="#af1e2d"/></g>
      ${text("#fff", 300, long ? 425 : 440, long ? 230 : 290)}`);
  }
  if (kind === "US") {
    return wrap("-12 -12 624 624", `<path d="${US_ROUTE}" fill="#fff" stroke="#111" stroke-width="30" stroke-linejoin="round"/>
      ${text("#111", 300, long ? 380 : 405, long ? 222 : 300)}`);
  }
  if (kind === "SR") {
    return wrap("-12 -4 409 409", `<path d="${CA_SPADE}" fill="#fff"/>
      <path d="${CA_SPADE}" fill="#006b54" transform="translate(192.5 215) scale(.92) translate(-192.5 -215)"/>
      ${text("#fff", 192.5, long ? 330 : 340, long ? 155 : 200)}`);
  }
  return wrap("0 0 600 600", `<rect width="600" height="600" rx="70" fill="#111"/><path d="${NEVADA}" fill="#fff"/>
    ${text("#111", 300, long ? 250 : 270, long ? 172 : 230)}`);
}

const LAND = [
  [900, [0.68, 0.62, 0.42]], [1500, [0.52, 0.53, 0.34]], [1900, [0.21, 0.37, 0.26]], [2300, [0.27, 0.40, 0.30]],
  [2700, [0.55, 0.53, 0.48]], [3300, [0.70, 0.68, 0.65]],
];
const WATER = [0.16, 0.42, 0.66];
const SNOW = [0.96, 0.975, 1.0];

function landColor(m, ramp) {
  if (m <= ramp[0][0]) return ramp[0][1];
  for (let i = 1; i < ramp.length; i++) {
    if (m <= ramp[i][0]) {
      const f = (m - ramp[i - 1][0]) / (ramp[i][0] - ramp[i - 1][0]);
      return ramp[i - 1][1].map((c, k) => c + f * (ramp[i][1][k] - c));
    }
  }
  return ramp[ramp.length - 1][1];
}

// Even-odd test against every ring at once, so holes and multi-part zones need no special handling.
function inRings(rings, x, y) {
  let inside = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
    }
  }
  return inside;
}
const rgbOf = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);

// The storm window around "now": back to the last full day without snow, forward to the next one.
export function stormWindow(rate, nowIndex) {
  const snowing = (i) => rate[i] >= DRY_RATE;
  const dryRun = (from, to) => { for (let i = from; i < to; i++) if (i >= 0 && i < rate.length && snowing(i)) return false; return true; };
  const active = !dryRun(nowIndex - DRY_GAP_H, nowIndex + 1) || !dryRun(nowIndex, nowIndex + 6);
  let start = nowIndex;
  if (active) while (start > 0 && !dryRun(start - DRY_GAP_H, start)) start--;
  const limit = Math.min(rate.length - 1, nowIndex + MAX_AHEAD_H);
  let end = nowIndex, seen = active;
  while (end < limit) {
    if (snowing(end)) seen = true;
    if (seen && dryRun(end, Math.min(rate.length, end + DRY_GAP_H))) break;
    end++;
  }
  if (!seen) end = Math.min(limit, nowIndex + 48);
  return {start, end: Math.max(end, nowIndex + 1), active};
}

// ``region`` says where the map is: {terrain, roads} data files, the disc's center [lat, lon], waterM (the level
// heights are drawn from), lake: {name, lat, lon}, and optionally land (its own colors by elevation), zoom
// (how close the view opens; 1 when absent), discKm (the disc's radius), and look ([lat, lon] the view opens on
// when that is not the disc's center).
// ``data.resorts`` holds only that region's locations.
// Below this many inches an hour, averaged over the region, it is not snowing: no flakes on the map, and the page says so.
const QUIET_RATE = 0.02;
export async function createMap(container, data, {region, onSelect, elevation = "summit", selected = null, globe = false, depth = {per: 1, unit: "in"}, freeTouch = () => false, finger = () => "spin"}) {
  const RADIUS = globe ? GLOBE_KM : region.discKm || DISC_KM, TARGET_Z = globe ? 7 : 1;
  // A region whose files were rebuilt carries a rev, so a phone never pairs the new page with its saved old files.
  const rev = region.rev || "";
  const [meta, buffer, roads] = await Promise.all([
    fetch(`${region.terrain}.json${rev}`).then((r) => r.json()),
    fetch(`${region.terrain}.bin${rev}`).then((r) => r.arrayBuffer()),
    fetch(region.roads + rev).then((r) => r.ok ? r.json() : []).catch(() => []),
  ]);
  const heights = new Uint16Array(buffer);
  const {rows, columns, width_km: W, height_km: H} = meta;
  const zOf = (m) => (Math.max(m, FLOOR_M) - region.waterM) / 1000 * EXAGGERATION;
  const xOf = (lon) => ((lon - meta.lon_w) / (meta.lon_e - meta.lon_w) - 0.5) * W;
  const yOf = (lat) => ((lat - meta.lat_s) / (meta.lat_n - meta.lat_s) - 0.5) * H;
  const heightAt = (lat, lon) => {
    const fr = Math.min(rows - 1.001, Math.max(0, (meta.lat_n - lat) / (meta.lat_n - meta.lat_s) * (rows - 1)));
    const fc = Math.min(columns - 1.001, Math.max(0, (lon - meta.lon_w) / (meta.lon_e - meta.lon_w) * (columns - 1)));
    const r = Math.floor(fr), c = Math.floor(fc), a = fr - r, b = fc - c, i = r * columns + c;
    return heights[i] * (1 - a) * (1 - b) + heights[i + 1] * (1 - a) * b + heights[i + columns] * a * (1 - b) + heights[i + columns + 1] * a * b;
  };

  // ---------- scene ----------
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 1, 1000);
  camera.up.set(0, 0, 1);
  const look = region.look || region.center, [centerLat, centerLon] = globe ? look : region.center;
  const lakeX = xOf(centerLon), lakeY = yOf(centerLat), lookX = xOf(look[1]), lookY = yOf(look[0]);
  const inGlobe = (x, y, margin = 0) => Math.hypot(x - lakeX, y - lakeY) < RADIUS - margin;
  // 1 well inside the disc, falling to 0 at its edge: a hard cut for the globe, a soft fade otherwise.
  const cover = (x, y) => {
    const inside = RADIUS - Math.hypot(x - lakeX, y - lakeY);
    if (globe) return inside > 0 ? 1 : 0;
    const f = Math.min(1, Math.max(0, inside / DISC_FADE_KM));
    return f * f * (3 - 2 * f);
  };
  // A region whose mountains sit close together opens closer in (zoom under 1).
  const zoom = region.zoom || 1;
  if (globe) camera.position.set(lakeX - 8, lakeY - 150, 104); else {
    // The camera starts south of the target; a region can swing it around (45 looks from the southeast).
    const turn = (region.turnDeg || 0) * Math.PI / 180, dx = -6 * zoom, dy = -100 * zoom;
    camera.position.set(lookX + dx * Math.cos(turn) - dy * Math.sin(turn), lookY - 4 + dx * Math.sin(turn) + dy * Math.cos(turn), 1 + 77 * zoom);
  }
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(lookX, lookY - (globe ? 0 : 4), TARGET_Z);
  controls.enableDamping = true;
  controls.enablePan = true;
  controls.screenSpacePanning = false;
  controls.minPolarAngle = Math.PI * 0.12;
  controls.maxPolarAngle = Math.PI * 0.40;
  // Panning stays over the terrain and at water level.
  controls.addEventListener("change", () => {
    const t = controls.target, d = Math.hypot(t.x - lakeX, t.y - lakeY), reach = RADIUS * 0.75;
    const x = d > reach ? lakeX + (t.x - lakeX) * reach / d : t.x, y = d > reach ? lakeY + (t.y - lakeY) * reach / d : t.y;
    if (x !== t.x || y !== t.y || t.z !== TARGET_Z) { camera.position.x += x - t.x; camera.position.y += y - t.y; t.set(x, y, TARGET_Z); }
  });
  controls.minDistance = 40;
  controls.maxDistance = globe ? 260 : 190 * RADIUS / DISC_KM;
  controls.zoomSpeed = 0.6;
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- gestures: one finger and a plain scroll wheel belong to the page; two fingers move the map ----------
  // Where the page says it is not scrolling (freeTouch), one finger slides the map and a plain wheel zooms it.
  const canvas = renderer.domElement;
  controls.touches = {ONE: -1, TWO: -1};
  canvas.style.touchAction = "pan-y";
  canvas.addEventListener("wheel", (e) => { if (!freeTouch() && !e.ctrlKey && !e.metaKey) e.stopImmediatePropagation(); }, {capture: true});
  let lastTouch = 0, gesture = null, single = null;
  const oneFinger = (e) => freeTouch() && e.touches.length === 1 ? {x: e.touches[0].clientX, y: e.touches[0].clientY} : null;
  const UP = new THREE.Vector3(0, 0, 1);
  const twoFingers = (e) => {
    const [a, b] = e.touches;
    return {x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2,
      span: Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY), angle: Math.atan2(b.clientY - a.clientY, b.clientX - a.clientX)};
  };
  canvas.addEventListener("touchstart", (e) => { gesture = e.touches.length === 2 ? twoFingers(e) : null; single = oneFinger(e); lastTouch = performance.now(); }, {passive: true});
  canvas.addEventListener("touchend", (e) => { gesture = e.touches.length === 2 ? twoFingers(e) : null; single = oneFinger(e); lastTouch = performance.now(); }, {passive: true});
  canvas.addEventListener("touchmove", (e) => {
    if (e.touches.length === 1 && single) {
      e.preventDefault();
      // One finger turns the map about the point it is looking at (the default: sideways turns it, up and down tilts
      // it), or, when the reader has chosen "pan", slides the ground under it the same as the two-finger drag.
      if (finger() === "spin") {
        const now = oneFinger(e), offset = camera.position.clone().sub(controls.target);
        offset.applyAxisAngle(UP, -(now.x - single.x) * 2 * Math.PI / canvas.clientWidth * 0.6);
        const length = offset.length(), flatReach = Math.hypot(offset.x, offset.y), heading = Math.atan2(offset.y, offset.x);
        const polar = Math.min(controls.maxPolarAngle, Math.max(controls.minPolarAngle, Math.atan2(flatReach, offset.z) - (now.y - single.y) * Math.PI / canvas.clientHeight * 0.5));
        offset.set(Math.sin(polar) * Math.cos(heading) * length, Math.sin(polar) * Math.sin(heading) * length, Math.cos(polar) * length);
        camera.position.copy(controls.target).add(offset);
        single = now; lastTouch = performance.now();
        controls.dispatchEvent({type: "change"});
        return;
      }
      const at = oneFinger(e), reach = camera.position.distanceTo(controls.target);
      const scale = 2 * reach * Math.tan(camera.fov * Math.PI / 360) / canvas.clientHeight;
      const across = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0).setZ(0).normalize();
      const along = new THREE.Vector3().crossVectors(UP, across);
      const move = across.multiplyScalar(-(at.x - single.x) * scale).add(along.multiplyScalar((at.y - single.y) * scale));
      controls.target.add(move); camera.position.add(move);
      single = at; lastTouch = performance.now();
      controls.dispatchEvent({type: "change"});
      return;
    }
    if (e.touches.length !== 2 || !gesture) return;
    e.preventDefault();
    const now = twoFingers(e), offset = camera.position.clone().sub(controls.target);
    // Twist turns the map with the fingers; pinch zooms; dragging slides the ground under them.
    let twist = now.angle - gesture.angle;
    if (twist > Math.PI) twist -= 2 * Math.PI; else if (twist < -Math.PI) twist += 2 * Math.PI;
    offset.applyAxisAngle(UP, twist);
    const distance = Math.min(controls.maxDistance, Math.max(controls.minDistance, offset.length() * gesture.span / Math.max(now.span, 1)));
    offset.setLength(distance);
    const perPixel = 2 * distance * Math.tan(camera.fov * Math.PI / 360) / canvas.clientHeight;
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0).setZ(0).normalize();
    const ahead = new THREE.Vector3().crossVectors(UP, right);
    const slide = right.multiplyScalar(-(now.x - gesture.x) * perPixel).add(ahead.multiplyScalar((now.y - gesture.y) * perPixel));
    controls.target.add(slide);
    camera.position.copy(controls.target).add(offset);
    gesture = now; lastTouch = performance.now();
    controls.dispatchEvent({type: "change"});
  }, {passive: false});

  // ---------- idle sway: a slow swing of 20 degrees each way once nobody has touched the map for a few seconds ----------
  const SWAY_DEG = 20, SWAY_PERIOD_S = 48, IDLE_S = 5;
  let dragging = false, lastInput = -Infinity, swayClock = 0, swayEase = 0;
  controls.addEventListener("start", () => { dragging = true; });
  controls.addEventListener("end", () => { dragging = false; lastInput = performance.now(); });
  const sway = (t, dt) => {
    const idle = !calm && !dragging && !gesture && !glide && !flat && t - Math.max(lastInput, lastTouch) > IDLE_S * 1000;
    if (!idle) { swayEase = 0; swayClock = 0; return; }
    swayEase = Math.min(1, swayEase + dt / 3);
    const before = Math.sin(2 * Math.PI * swayClock / SWAY_PERIOD_S);
    swayClock += dt;
    const step = (Math.sin(2 * Math.PI * swayClock / SWAY_PERIOD_S) - before) * SWAY_DEG * Math.PI / 180 * swayEase;
    camera.position.sub(controls.target).applyAxisAngle(UP, step).add(controls.target);
  };
  // ---------- north up, and the flat view from straight above ----------
  // The camera's place around its target: how far, how tilted from straight above, and how far turned from north-up.
  const pose = () => {
    const o = camera.position.clone().sub(controls.target), r = o.length();
    return {r, polar: Math.acos(Math.min(1, Math.max(-1, o.z / r))), turn: Math.atan2(o.x, -o.y)};
  };
  const setPose = ({r, polar, turn}) => camera.position.set(
    controls.target.x + r * Math.sin(polar) * Math.sin(turn), controls.target.y - r * Math.sin(polar) * Math.cos(turn), controls.target.z + r * Math.cos(polar));
  const TILT_MIN = controls.minPolarAngle, TILT_MAX = controls.maxPolarAngle, HOME_POLAR = pose().polar, FLAT_POLAR = 0.02, GLIDE_MS = 450;
  let flat = false, glide = null;
  const settle = () => { controls.minPolarAngle = flat ? 0 : TILT_MIN; controls.maxPolarAngle = flat ? FLAT_POLAR : TILT_MAX; lastInput = performance.now(); };
  // Eases the camera to a new tilt and turn, the short way round. The tilt limits open up while it moves.
  const glideTo = (to) => {
    const from = pose();
    let swing = (to.turn ?? from.turn) - from.turn;
    swing -= 2 * Math.PI * Math.round(swing / (2 * Math.PI));
    const goal = {r: from.r, polar: to.polar ?? from.polar, turn: from.turn + swing};
    controls.minPolarAngle = 0; controls.maxPolarAngle = TILT_MAX;
    if (calm) { setPose(goal); settle(); return; }
    glide = {from, goal, began: performance.now()};
  };
  const stepGlide = (t) => {
    if (!glide) return;
    const f = Math.min(1, (t - glide.began) / GLIDE_MS), e = f * f * (3 - 2 * f), {from, goal} = glide;
    setPose({r: pose().r, polar: from.polar + (goal.polar - from.polar) * e, turn: from.turn + (goal.turn - from.turn) * e});
    if (f >= 1) { glide = null; settle(); }
  };
  scene.add(new THREE.HemisphereLight(0xe8f1fa, 0x6b6253, 1.15));
  const sun = new THREE.DirectionalLight(0xfff4e2, 2.1);
  sun.position.set(-70, 60, 55);
  scene.add(sun);

  // ---------- terrain (fades out toward its edges, so there is no hard rim) ----------
  const count = rows * columns;
  const positions = new Float32Array(count * 3), colors = new Float32Array(count * 4), base = new Float32Array(count * 3);
  const water = new Uint8Array(count);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < columns; c++) {
      const i = r * columns + c, m = heights[i];
      const x = (c / (columns - 1) - 0.5) * W, y = (0.5 - r / (rows - 1)) * H;
      positions.set([x, y, zOf(m)], 3 * i);
      colors[4 * i + 3] = cover(x, y);
      const flat = (j) => Math.abs(heights[j] - m) < 0.6;
      // Level ground is a lake in the mountains, but in the Central Valley it is only farmland.
      water[i] = m >= LOWLAND_M && r > 0 && r < rows - 1 && c > 0 && c < columns - 1 && flat(i - 1) && flat(i + 1) && flat(i - columns) && flat(i + columns) ? 1 : 0;
    }
  }
  const shore = water.slice();
  for (let i = columns; i < count - columns; i++) if (!water[i] && (water[i - 1] || water[i + 1] || water[i - columns] || water[i + columns]) && Math.abs(heights[i] - heights[i - 1]) < 2) shore[i] = 1;
  for (let i = 0; i < count; i++) {
    base.set(shore[i] ? WATER : landColor(heights[i], region.land || LAND), 3 * i);
    colors.set(base.subarray(3 * i, 3 * i + 3), 4 * i);
  }
  const index = new Uint32Array((rows - 1) * (columns - 1) * 6);
  let k = 0;
  for (let r = 0; r < rows - 1; r++) for (let c = 0; c < columns - 1; c++) {
    const a = r * columns + c, b = a + 1, d = a + columns, e = d + 1;
    index.set([a, d, b, b, d, e], k); k += 6;
  }
  const terrain = new THREE.BufferGeometry();
  terrain.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  terrain.setAttribute("color", new THREE.BufferAttribute(colors, 4));
  terrain.setIndex(new THREE.BufferAttribute(index, 1));
  terrain.computeVertexNormals();
  const ground = new THREE.Mesh(terrain, new THREE.MeshStandardMaterial({vertexColors: true, roughness: 0.92, metalness: 0, ...(globe ? {alphaTest: 0.5} : {transparent: true})}));
  ground.renderOrder = 1;
  scene.add(ground);

  // ---------- the globe: a rim wall where the terrain is cut, a base, and a glass dome ----------
  const floorZ = zOf(FLOOR_M) - 0.8, SEGMENTS = 360;
  if (globe) {
    const rim = new Float32Array((SEGMENTS + 1) * 6), rimIndex = [];
    for (let n = 0; n <= SEGMENTS; n++) {
      const a = n / SEGMENTS * Math.PI * 2, x = lakeX + Math.cos(a) * (GLOBE_KM - 0.15), y = lakeY + Math.sin(a) * (GLOBE_KM - 0.15);
      const lon = meta.lon_w + (x / W + 0.5) * (meta.lon_e - meta.lon_w), lat = meta.lat_s + (y / H + 0.5) * (meta.lat_n - meta.lat_s);
      rim.set([x, y, zOf(heightAt(lat, lon)) + 0.05, x, y, floorZ], n * 6);
      if (n) rimIndex.push(2 * n - 2, 2 * n - 1, 2 * n, 2 * n, 2 * n - 1, 2 * n + 1);
    }
    const rimGeometry = new THREE.BufferGeometry();
    rimGeometry.setAttribute("position", new THREE.BufferAttribute(rim, 3));
    rimGeometry.setIndex(rimIndex); rimGeometry.computeVertexNormals();
    scene.add(new THREE.Mesh(rimGeometry, new THREE.MeshStandardMaterial({color: 0x59534a, roughness: 1, side: THREE.DoubleSide})));
    const pedestal = new THREE.Mesh(new THREE.CylinderGeometry(GLOBE_KM * 1.04, GLOBE_KM * 1.09, 3, 96).rotateX(Math.PI / 2),
      new THREE.MeshStandardMaterial({color: 0x2b333c, roughness: 0.45, metalness: 0.35}));
    pedestal.position.set(lakeX, lakeY, floorZ - 1.5);
    scene.add(pedestal);
    const dome = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_KM * 1.02, 96, 48, 0, Math.PI * 2, 0, Math.PI / 2).rotateX(Math.PI / 2),
      new THREE.MeshPhysicalMaterial({color: 0xffffff, transparent: true, opacity: 0.13, roughness: 0.02, metalness: 0, clearcoat: 1,
        clearcoatRoughness: 0.03, side: THREE.DoubleSide, depthWrite: false}));
    dome.scale.z = DOME_SQUASH;
    dome.position.set(lakeX, lakeY, floorZ);
    dome.renderOrder = 4;
    scene.add(dome);
  }
  // Top of the falling snow: the glass in the globe, a high flat ceiling otherwise.
  const domeTop = (x, y) => globe ? floorZ + DOME_SQUASH * Math.sqrt(Math.max(0, GLOBE_KM * GLOBE_KM - (x - lakeX) ** 2 - (y - lakeY) ** 2)) : SKY_KM;

  // ---------- forecast series and the storm window ----------
  const hoursUtc = data.resorts[0].hours_utc, total = hoursUtc.length;
  const nowMs = new Date(data.generated_utc).getTime();
  const nowIndex = Math.max(0, hoursUtc.findIndex((t) => new Date(t).getTime() >= nowMs));
  const rate = new Float32Array(total), snowLevel = new Float32Array(total);
  for (let i = 0; i < total; i++) {
    let sum = 0, lv = 0, n = 0;
    for (const r of data.resorts) {
      const h = r.elevations.summit.hourly;
      sum += h.snow_in[i] || 0;
      if (h.snow_level_ft[i] != null) { lv += h.snow_level_ft[i] * 0.3048; n++; }
    }
    rate[i] = sum / data.resorts.length; snowLevel[i] = n ? lv / n : 9999;
  }
  const storm = stormWindow(rate, nowIndex);
  const steps = storm.end - storm.start + 1, nowStep = nowIndex - storm.start;
  let level = elevation;
  const series = () => data.resorts.map((r) => {
    const h = r.elevations[level].hourly, cum = new Float32Array(steps);
    for (let i = 1; i < steps; i++) cum[i] = cum[i - 1] + (h.snow_in[storm.start + i - 1] || 0);
    return cum;
  });
  let cumulative = series();
  // Fresh snow by elevation band: each hour's snowfall lands on everything above that hour's snow level.
  const bins = Math.ceil(meta.max_m / BIN_M) + 1;
  const fresh = Array.from({length: steps}, () => new Float32Array(bins));
  for (let i = 1; i < steps; i++) {
    const h = storm.start + i - 1;
    for (let b = 0; b < bins; b++) {
      const above = Math.min(1, Math.max(0, (b * BIN_M - (snowLevel[h] - 100)) / 200));
      fresh[i][b] = fresh[i - 1][b] + rate[h] * above;
    }
  }
  // The snow already on the ground, by elevation band, read off the region's depth sensors: nothing below a snow line,
  // then deeper with height in a straight line through the sensors' average. The snow line is the highest sensor
  // reading bare ground, or, when even the lowest has snow, a way below it (further the deeper its snow, 1,500 ft at most).
  const pack = new Float32Array(bins);
  {
    const seen = new Map();
    for (const r of data.resorts) {
      const o = r.observed;
      if (o && o.depth_in != null && o.elevation_ft != null) seen.set(o.station, [o.elevation_ft, o.depth_in]);
    }
    const all = [...seen.values()], snowy = all.filter(([, d]) => d >= 1), bare = all.filter(([, d]) => d < 1);
    if (snowy.length) {
      const mean = (k) => snowy.reduce((sum, p) => sum + p[k], 0) / snowy.length;
      const low = snowy.reduce((a, p) => p[0] < a[0] ? p : a);
      const under = bare.filter(([ft]) => ft < low[0]).map(([ft]) => ft);
      const line = under.length ? Math.max(...under) : low[0] - Math.min(1500, low[1] * 50);
      const ft = Math.max(mean(0), line + 500), deep = mean(1);
      for (let b = 0; b < bins; b++) pack[b] = Math.min(2 * deep, Math.max(0, deep * (b * BIN_M / 0.3048 - line) / (ft - line)));
    }
  }

  // ---------- roads ----------
  const overlay = document.createElement("div");
  overlay.className = "map-labels";
  container.appendChild(overlay);
  const compass = document.createElement("div");
  compass.className = "map-compass"; compass.title = "The red end points north. Tap to face north.";
  compass.setAttribute("role", "button"); compass.setAttribute("aria-label", "Face north"); compass.tabIndex = 0;
  compass.style.pointerEvents = "auto"; compass.style.cursor = "pointer";
  compass.addEventListener("click", () => glideTo({turn: 0}));
  compass.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); glideTo({turn: 0}); } });
  compass.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5 15.2 12H8.8z" fill="#d6322f"/><path d="M12 21.5 8.8 12h6.4z" fill="#8a929b"/><circle cx="12" cy="12" r="1.3" fill="#fff"/></svg>';
  container.appendChild(compass);
  const needle = compass.firstChild;
  const roadPoints = [];
  const roadPositions = [], roadIndex = [];
  const shields = [], roadLines = [];
  for (const road of roads) {
    const half = (MAJOR.has(road.route) ? 0.42 : 0.3);
    for (const line of road.lines) {
      // Resample so the ribbon follows the terrain.
      const pts = [];
      for (let i = 0; i < line.length; i++) {
        const [lon, lat] = line[i];
        if (i) {
          const [plon, plat] = line[i - 1];
          const d = Math.hypot(xOf(lon) - xOf(plon), yOf(lat) - yOf(plat)), n = Math.max(1, Math.ceil(d / 0.6));
          for (let s = 1; s < n; s++) pts.push([plon + (lon - plon) * s / n, plat + (lat - plat) * s / n]);
        }
        pts.push([lon, lat]);
      }
      roadLines.push({route: road.route, pts});
      const startVertex = roadPositions.length / 3;
      pts.forEach(([lon, lat], i) => {
        const x = xOf(lon), y = yOf(lat), z = zOf(heightAt(lat, lon)) + ROAD_LIFT;
        const [nlon, nlat] = pts[Math.min(pts.length - 1, i + 1)], [plon, plat] = pts[Math.max(0, i - 1)];
        let dx = xOf(nlon) - xOf(plon), dy = yOf(nlat) - yOf(plat);
        const len = Math.hypot(dx, dy) || 1; dx /= len; dy /= len;
        roadPositions.push(x - dy * half, y + dx * half, z, x + dy * half, y - dx * half, z);
        roadPoints.push({route: road.route, lon, lat});
        if (i) { const a = startVertex + 2 * (i - 1); roadIndex.push(a, a + 1, a + 2, a + 2, a + 1, a + 3); }
      });
    }
  }

  // Route shields in their real shapes, spaced along each road and kept clear of the resorts and each other.
  // Short routes go first so they keep a spot.
  const SHIELD_ORDER = ["SR-203", "SR-158", "SR-267", "NV-207", "NV-431", "SR-28", "NV-28", "SR-167", "SR-270", "SR-182", "I-80", "US-50", "SR-89", "SR-88",
    "US-395", "I-580", "SR-49", "SR-20", "SR-4", "SR-120", "SR-108", "SR-168", "US-6"];
  const placedShields = [];
  for (const route of SHIELD_ORDER) {
    for (const pts of roadLines.filter((line) => line.route === route).map((line) => line.pts).sort((a, b) => b.length - a.length)) {
      const step = Math.round(SHIELD_EVERY_KM / 0.6);
      // A short road gets one shield, at the first spot that is free.
      const short = pts.length < step;
      const picks = short ? (pts.length > 8 ? [0.5, 0.35, 0.65, 0.2, 0.8].map((f) => Math.floor(pts.length * f)) : [])
        : Array.from({length: Math.floor(pts.length / step)}, (_, n) => Math.floor(step / 2) + n * step);
      let placedHere = 0;
      for (const index of picks) {
        if (short && placedHere) break;
        const [lon, lat] = pts[index], x = xOf(lon), y = yOf(lat);
        if (cover(x, y) < 0.95) continue;
        if (placedShields.some((q) => Math.hypot(q.x - x, q.y - y) < (q.route === route ? 18 : short ? 3.5 : 5))) continue;
        if (data.resorts.some((r) => Math.hypot(xOf(r.lon) - x, yOf(r.lat) - y) < 2.2)) continue;
        const tag = document.createElement("div");
        tag.className = "map-shield"; tag.innerHTML = shieldSVG(route); tag.title = route;
        overlay.appendChild(tag);
        placedShields.push({route, x, y});
        placedHere++;
        shields.push({tag, point: new THREE.Vector3(x, y, zOf(heightAt(lat, lon)) + 0.5), inside: true});
      }
    }
  }
  const roadColors = new Float32Array(roadPoints.length * 2 * 4);
  const roadGeometry = new THREE.BufferGeometry();
  roadGeometry.setAttribute("position", new THREE.Float32BufferAttribute(roadPositions, 3));
  roadGeometry.setAttribute("color", new THREE.BufferAttribute(roadColors, 4));
  roadGeometry.setIndex(roadIndex);
  const paintRoads = (statusOf) => {
    roadPoints.forEach((p, i) => {
      const rgb = ROAD_COLORS[statusOf(p)] || ROAD_COLORS.open;
      const x = xOf(p.lon), y = yOf(p.lat);
      const fade = cover(x, y);
      roadColors.set([...rgb, fade, ...rgb, fade], 8 * i);
    });
    roadGeometry.attributes.color.needsUpdate = true;
  };
  paintRoads(() => "open");
  // Drawn after the terrain from every angle, so the ribbons never vanish behind it.
  const ribbons = new THREE.Mesh(roadGeometry, new THREE.MeshBasicMaterial({vertexColors: true, side: THREE.DoubleSide, depthWrite: false, ...(globe ? {alphaTest: 0.5} : {transparent: true})}));
  ribbons.renderOrder = 2;
  scene.add(ribbons);
  const closures = [];

  // ---------- resorts ----------
  const stakes = new THREE.Group();
  scene.add(stakes);
  const ghostMaterial = new THREE.MeshBasicMaterial({color: 0x2a78d6, transparent: true, opacity: 0.25, depthWrite: false});
  const fillMaterial = new THREE.MeshStandardMaterial({color: 0x2a78d6, roughness: 0.4, emissive: 0x0d366b, emissiveIntensity: 0.5});
  const pickMaterial = new THREE.MeshStandardMaterial({color: 0xffffff, roughness: 0.4, emissive: 0x2a78d6, emissiveIntensity: 0.9});
  const unit = new THREE.CylinderGeometry(STAKE_RADIUS, STAKE_RADIUS, 1, 20).rotateX(Math.PI / 2).translate(0, 0, 0.5);
  const items = data.resorts.map((r, n) => {
    const x = xOf(r.lon), y = yOf(r.lat), z = zOf(heightAt(r.lat, r.lon));
    const ghost = new THREE.Mesh(unit, ghostMaterial), fill = new THREE.Mesh(unit, fillMaterial);
    ghost.position.set(x, y, z); fill.position.set(x, y, z);
    stakes.add(ghost, fill);
    const label = document.createElement("button");
    label.className = "map-label";
    label.addEventListener("click", () => onSelect && onSelect(r.key));
    overlay.appendChild(label);
    // The snow on the ground now, where the mountain's sensor measures it; null where none does.
    const ground = r.observed && r.observed.depth_in != null ? r.observed.depth_in : null;
    return {key: r.key, name: r.name, backcountry: r.kind === "backcountry", ground, x, y, z, ghost, fill, label, n, top: new THREE.Vector3(), width: 80, tall: 40};
  });
  const lake = document.createElement("div");
  lake.className = "map-lake"; lake.textContent = region.lake.name;
  overlay.appendChild(lake);
  const lakeAt = new THREE.Vector3(xOf(region.lake.lon), yOf(region.lake.lat), zOf(heightAt(region.lake.lat, region.lake.lon)) + 0.1);

  // ---------- avalanche danger: each zone's rating tints the terrain inside its outline ----------
  // zoneOf holds, per terrain vertex, the zone it falls in (1-based; 0 for none), worked out once per set of zones.
  const zoneOf = new Uint8Array(count);
  let dangerColors = [], dangerOn = false;
  function setAvalanche(zones) {
    zoneOf.fill(0);
    dangerColors = zones.map((zone) => rgbOf(zone.color));
    zones.forEach((zone, n) => {
      const rings = zone.rings.map((ring) => ring.map(([lon, lat]) => [xOf(lon), yOf(lat)]));
      const xs = rings.flat().map((p) => p[0]), ys = rings.flat().map((p) => p[1]);
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      for (let v = 0; v < count; v++) {
        const x = positions[3 * v], y = positions[3 * v + 1];
        if (x < x0 || x > x1 || y < y0 || y > y1 || !inRings(rings, x, y)) continue;
        zoneOf[v] = n + 1;
      }
    });
    paintedAt = -1;
  }

  // ---------- falling snow (fills the whole view, from well above the peaks) ----------
  const flakePositions = new Float32Array(FLAKES * 3), flakeSpeed = new Float32Array(FLAKES);
  const flakeSize = new Float32Array(FLAKES), flakeSeed = new Float32Array(FLAKES);
  for (let i = 0; i < FLAKES; i++) {
    const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * (globe ? GLOBE_KM - 1.5 : RADIUS * 1.15), x = lakeX + Math.cos(a) * d, y = lakeY + Math.sin(a) * d;
    flakePositions.set([x, y, floorZ + Math.random() * (domeTop(x, y) - floorZ)], 3 * i);
    // Mostly fine flakes, with the odd fat one drifting down slowly close to the eye.
    const fat = Math.random() < 0.05, r = Math.random();
    flakeSize[i] = fat ? 0.9 + r * 0.7 : 0.28 + r * r * 0.5;
    flakeSpeed[i] = fat ? 1.6 + r : 2.5 + Math.random() * 3.5;
    flakeSeed[i] = Math.random();
  }
  const flakeGeometry = new THREE.BufferGeometry();
  flakeGeometry.setAttribute("position", new THREE.BufferAttribute(flakePositions, 3));
  flakeGeometry.setAttribute("size", new THREE.BufferAttribute(flakeSize, 1));
  flakeGeometry.setAttribute("seed", new THREE.BufferAttribute(flakeSeed, 1));
  // Soft round flakes: each drifts sideways on its own rhythm, the fat ones are blurred like something out of focus,
  // and one too small to draw as a disc fades instead of flickering.
  const flakeLook = {opacity: {value: 0}, clock: {value: 0}, tall: {value: 1}};
  const flakeMaterial = new THREE.ShaderMaterial({
    uniforms: flakeLook, transparent: true, depthWrite: false,
    vertexShader: `
      attribute float size; attribute float seed;
      uniform float clock; uniform float tall;
      varying float vAlpha; varying float vBlur;
      void main() {
        float turn = seed * 6.2832;
        vec3 p = position + vec3(sin(clock * (0.5 + seed) + turn), cos(clock * (0.4 + seed * 0.7) + turn * 1.7), 0.0) * (0.25 + size * 0.5);
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        float px = size * projectionMatrix[1][1] * tall * 0.5 / -mv.z;
        gl_PointSize = max(px, 2.0);
        vBlur = smoothstep(0.7, 1.4, size);
        vAlpha = (0.55 + 0.45 * fract(seed * 7.31)) * min(1.0, px / 2.0) * mix(1.0, 0.55, vBlur);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform float opacity;
      varying float vAlpha; varying float vBlur;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        float disc = smoothstep(1.0, mix(0.45, 0.0, vBlur), d);
        gl_FragColor = vec4(1.0, 1.0, 1.0, disc * vAlpha * opacity);
      }`,
  });
  const snowfall = new THREE.Points(flakeGeometry, flakeMaterial);
  snowfall.renderOrder = 3;
  snowfall.frustumCulled = false;
  scene.add(snowfall);

  // ---------- state ----------
  let time = nowStep, paintedAt = -1, picked = selected, visible = true, running = true;
  const interp = (array, t, offset = 0) => {
    const i = Math.min(array.length - 1, Math.floor(t) + offset), j = Math.min(array.length - 1, i + 1), f = t - Math.floor(t);
    return array[i] + f * (array[j] - array[i]);
  };
  const show = (v) => v < 0.05 ? "0" : v < 0.5 ? "<1" : String(Math.round(v));

  function paint() {
    const i = Math.min(steps - 1, Math.floor(time)), j = Math.min(steps - 1, i + 1), f = time - i;
    const nowAt = Math.max(0, Math.min(steps - 1, Math.round(nowStep)));
    for (let v = 0; v < count; v++) {
      if (shore[v]) continue;
      const b = Math.min(bins - 1, Math.floor(heights[v] / BIN_M));
      const fell = fresh[i][b] + f * (fresh[j][b] - fresh[i][b]);
      // Looking back into the storm, the snow lying then is today's less what has fallen since.
      const lying = Math.max(0, pack[b] - Math.max(0, fresh[nowAt][b] - fell));
      const amount = fell + lying * WHITEN_AT_IN / PACK_WHITE_IN;
      const w = Math.min(1, amount / WHITEN_AT_IN), s = w * w * (3 - 2 * w);
      const tint = dangerOn && zoneOf[v] ? dangerColors[zoneOf[v] - 1] : null;
      for (let k = 0; k < 3; k++) {
        const land = base[3 * v + k] + s * (SNOW[k] - base[3 * v + k]);
        colors[4 * v + k] = tint ? land + DANGER_TINT * (tint[k] - land) : land;
      }
    }
    terrain.attributes.color.needsUpdate = true;
    for (const item of items) {
      const all = cumulative[item.n][steps - 1], value = interp(cumulative[item.n], time);
      item.fill.scale.z = Math.max(0.02, value * STAKE_KM_PER_IN);
      // The snow still to come stands on top of the snow so far; two stakes sharing one surface flicker.
      item.ghost.visible = all - value > 0.05;
      item.ghost.position.z = item.z + item.fill.scale.z;
      item.ghost.scale.z = Math.max(0.02, (all - value) * STAKE_KM_PER_IN);
      item.fill.material = item.key === picked ? pickMaterial : fillMaterial;
      const more = all - value;
      // The number is the snow on the ground now, where a sensor measures it; under it the storm plays: what has
      // fallen by the time shown and what is still to come. With no depth measured the storm's snow is the number.
      const d = depth.per, fell = value >= 0.05, coming = more >= 0.5;
      const head = item.ground == null ? `${show(value * d)} ${depth.unit} new` : `${show(item.ground * d)} ${depth.unit}`;
      const under = item.ground == null ? (coming ? `+${show(more * d)} to come` : "")
        : fell && coming ? `${show(value * d)} new · +${show(more * d)} to come` : fell ? `${show(value * d)} ${depth.unit} new` : coming ? `+${show(more * d)} to come` : "";
      item.label.innerHTML = `<b>${item.name}</b><span>${head}</span>${under ? `<em>${under}</em>` : ""}`;
      item.label.classList.toggle("on", item.key === picked);
      item.label.title = item.name;
      item.width = 16 + Math.max(item.name.length * 6.6, under.length * 5.6, item.ground == null ? 66 : 44);
      item.tall = under ? 54 : 40;
    }
    // Flakes fall only at a rate the caption also calls snow; under it, both say it is not snowing.
    const falling = interp(rate, time, storm.start);
    flakeLook.opacity.value = falling < QUIET_RATE ? 0 : Math.min(0.95, falling * 3.2);
    paintedAt = time;
  }

  function placeLabels() {
    const w = container.clientWidth, h = container.clientHeight;
    const project = (point) => {
      const p = point.clone().project(camera);
      return {x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, depth: p.z, shown: p.z < 1 && Math.abs(p.x) < 1.02 && Math.abs(p.y) < 1.02};
    };
    // The selected and nearest labels are placed first; one that would cover another shrinks to its number, then steps up.
    const placed = [];
    const hits = (r) => placed.some((q) => r.x0 < q.x1 && r.x1 > q.x0 && r.y0 < q.y1 && r.y1 > q.y0);
    const order = items.map((item) => {
      item.top.set(item.x, item.y, item.z + Math.max(item.fill.scale.z, 0.02) + 0.7);
      return {item, p: project(item.top)};
    }).sort((a, b) => (b.item.key === picked) - (a.item.key === picked) || a.item.backcountry - b.item.backcountry || a.p.depth - b.p.depth);
    for (const {item, p} of order) {
      const label = item.label;
      label.style.display = p.shown ? "" : "none";
      if (!p.shown) continue;
      const box = (width, height, lift) => ({x0: p.x - width / 2 - 2, x1: p.x + width / 2 + 2, y0: p.y - height - 6 - lift, y1: p.y - lift});
      let mini = false, rect = box(item.width, item.tall, 0);
      if (hits(rect)) { mini = true; rect = box(46, 24, 0); }
      // A label that still collides is hidden rather than floated away from its stake.
      if (hits(rect)) { label.style.display = "none"; continue; }
      placed.push(rect);
      label.classList.toggle("mini", mini);
      label.style.transform = `translate3d(${p.x.toFixed(2)}px, ${(p.y - 6).toFixed(2)}px, 0) translate(-50%, -100%)`;
      label.style.zIndex = String(100000 + Math.round((1 - p.depth) * 100000));
    }
    // Each tag is its own compositor layer (see the page's will-change rule), so it is drawn once and then
    // slid at fractional positions: the motion is smooth and text stays locked to its shape.
    const put = (element, point, allowed = true) => {
      const p = project(point);
      element.style.display = p.shown && allowed ? "" : "none";
      element.style.transform = `translate3d(${p.x.toFixed(2)}px, ${p.y.toFixed(2)}px, 0) translate(-50%, -50%)`;
    };
    put(lake, lakeAt);
    // A shield gives way to anything more important: a resort label, or a stake standing in front of it.
    const stakeLines = items.map((item) => [project(new THREE.Vector3(item.x, item.y, item.z)), project(item.top)]);
    for (const shield of shields) {
      const q = project(shield.point), box = {x0: q.x - 15, x1: q.x + 15, y0: q.y - 15, y1: q.y + 15};
      const behindStake = stakeLines.some(([a, b]) => Math.abs(q.x - (a.x + b.x) / 2) < 16 && q.y > Math.min(a.y, b.y) - 14 && q.y < Math.max(a.y, b.y) + 14);
      put(shield.tag, shield.point, shield.inside && !hits(box) && !behindStake);
    }
    for (const closure of closures) put(closure.tag, closure.point);
  }

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // Widen the lens on narrow screens so the whole lake stays in view.
    camera.fov = w < 520 ? 50 : 30;
    camera.updateProjectionMatrix();
  }
  const watchers = [new ResizeObserver(resize), new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; })];
  for (const watcher of watchers) watcher.observe(container);
  resize();

  let last = performance.now();
  function frame(t) {
    if (!running) return;
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (t - last) / 1000); last = t;
    if (!visible) return;
    if (paintedAt !== time) paint();
    if (flakeLook.opacity.value > 0.01 && !calm) {
      flakeLook.clock.value = t / 1000;
      for (let i = 0; i < FLAKES; i++) {
        let z = flakePositions[3 * i + 2] - flakeSpeed[i] * dt;
        if (z < 0) z = domeTop(flakePositions[3 * i], flakePositions[3 * i + 1]) - 0.5;
        flakePositions[3 * i + 2] = z;
      }
      flakeGeometry.attributes.position.needsUpdate = true;
    }
    flakeLook.tall.value = renderer.domElement.height;
    stepGlide(t);
    sway(t, dt);
    controls.update();
    renderer.render(scene, camera);
    placeLabels();
    // The needle's red end points north whichever way the map is turned.
    const ahead = controls.target.clone().sub(camera.position);
    needle.style.transform = `rotate(${(Math.atan2(-ahead.x, ahead.y) * 180 / Math.PI).toFixed(1)}deg)`;
  }
  requestAnimationFrame(frame);

  return {
    steps, nowStep, stormActive: storm.active,
    timeAt: (i) => new Date(hoursUtc[storm.start + Math.min(steps - 1, Math.max(0, Math.round(i)))]),
    rateAt: (i) => interp(rate, i, storm.start),
    quietRate: QUIET_RATE,
    snowLevelFtAt: (i) => interp(snowLevel, i, storm.start) / 0.3048,
    setTime(value) { time = Math.max(0, Math.min(steps - 1, value)); },
    setElevation(value) { level = value; cumulative = series(); paintedAt = -1; },
    // A better figure for the snow on the ground at some mountains (key: inches), in place of the sensor's.
    setGround(byKey) { for (const item of items) if (byKey[item.key] != null) item.ground = byKey[item.key]; paintedAt = -1; },
    select(key) { picked = key; paintedAt = -1; },
    // Depths are kept in inches; the labels show them times `per`, in `unit`.
    setDepthUnits(units) { depth = units; paintedAt = -1; },
    // controlPoints: [{route, lat, lon, status: "chains" | "closed", name}] from the Caltrans feeds; a closed
    // point with sign: false colors the road without getting a sign of its own.
    setRoadStatus(controlPoints) {
      const byRoute = {};
      for (const point of controlPoints) (byRoute[point.route] ||= []).push({...point, x: xOf(point.lon), y: yOf(point.lat)});
      paintRoads((p) => {
        const list = byRoute[p.route];
        if (!list) return "open";
        const x = xOf(p.lon), y = yOf(p.lat);
        let nearest = Infinity;
        for (const c of list) nearest = Math.min(nearest, Math.hypot(c.x - x, c.y - y));
        if (nearest > 7) return "open";
        let worst = "open";
        for (const c of list) {
          if (Math.hypot(c.x - x, c.y - y) > nearest + 1.5) continue;
          if (c.status === "closed") worst = "closed"; else if (worst === "open") worst = "chains";
        }
        return worst;
      });
      for (const closure of closures) closure.tag.remove();
      closures.length = 0;
      for (const point of controlPoints.filter((p) => p.status === "closed" && p.sign !== false)) {
        const x = xOf(point.lon), y = yOf(point.lat);
        if (!inGlobe(x, y, globe ? 1 : DISC_FADE_KM * 0.6)) continue;
        if (closures.some((c) => c.route === point.route && Math.hypot(c.x - x, c.y - y) < 6)) continue;
        const tag = document.createElement("div");
        tag.className = "map-closed"; tag.title = `Closed: ${point.route} ${point.name}`; tag.setAttribute("role", "img"); tag.setAttribute("aria-label", tag.title);
        tag.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="#fff"/><circle cx="12" cy="12" r="9.6" fill="#c8161d"/><rect x="5.2" y="9.9" width="13.6" height="4.2" rx=".6" fill="#fff"/></svg>';
        overlay.appendChild(tag);
        closures.push({tag, route: point.route, x, y, point: new THREE.Vector3(x, y, zOf(heightAt(point.lat, point.lon)) + 0.9)});
      }
    },
    // zones: [{rings: [[[lon, lat], ...], ...], color: "#rrggbb", ink, label, title}], one per avalanche forecast zone.
    setAvalanche,
    showAvalanche(on) { dangerOn = on; paintedAt = -1; },
    northUp() { glideTo({turn: 0}); },
    // Flat is the view from straight above, north up; leaving it tilts back to the opening angle.
    setFlat(on) { flat = on; glideTo(on ? {polar: FLAT_POLAR, turn: 0} : {polar: HOME_POLAR}); },
    dispose() {
      running = false;
      for (const watcher of watchers) watcher.disconnect();
      controls.dispose(); renderer.dispose();
      canvas.remove(); overlay.remove(); compass.remove();
    },
  };
}
