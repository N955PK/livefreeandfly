// 3D map of the Tahoe basin: real terrain, resorts as snow stakes for the current storm, and live road status.
// Scene units are kilometers; x is east, y is north, z is up.
import * as THREE from "three";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";

const EXAGGERATION = 2.7;
const STAKE_KM_PER_IN = 0.16;
const STAKE_RADIUS = 0.7;
const FLAKES = 9000;
const WHITEN_AT_IN = 5;
const BIN_M = 50;
const FLOOR_M = 1150;
const EDGE_FADE_KM = 16;
const GLOBE_KM = 50;
const DISC_KM = 72;
const DISC_FADE_KM = 10;
const SKY_KM = 110;
const DOME_SQUASH = 0.62;
const DRY_GAP_H = 12;
const DRY_RATE = 0.01;
const MAX_AHEAD_H = 96;
const ROAD_LIFT = 0.16;
const ROAD_COLORS = {open: [0.20, 0.23, 0.27], chains: [0.96, 0.66, 0.05], closed: [0.84, 0.18, 0.18]};
const MAJOR = new Set(["I-80", "US-50", "US-395", "I-580"]);
const SHIELD_EVERY_KM = 26;

// Interstate, U.S. route, California state route (the green spade), and Nevada state route markers.
function shieldSVG(route) {
  const [kind, number] = route.split("-"), size = number.length > 2 ? 7.2 : 9;
  const text = (fill, y) => `<text x="12" y="${y}" text-anchor="middle" font-size="${size}" font-weight="700" font-family="system-ui,-apple-system,sans-serif" fill="${fill}">${number}</text>`;
  const wrap = (inner) => `<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">${inner}</svg>`;
  if (kind === "I") {
    return wrap(`<path d="M12 1.2c2.9 1.5 5.9 1.9 9.2 1.3 1 6.9-.9 14.6-9.2 20.1C3.7 17.1 1.8 9.4 2.8 2.5 6.1 3.1 9.1 2.7 12 1.2z" fill="#003f87" stroke="#fff" stroke-width="1"/>
      <path d="M3.3 3.6C6.3 4 9.2 3.6 12 2.3c2.8 1.3 5.7 1.7 8.7 1.3-.1 1-.1 2-.1 2.9H3.4c0-.9 0-1.9-.1-2.9z" fill="#af1e2d"/>${text("#fff", 17.2)}`);
  }
  if (kind === "US") {
    return wrap(`<path d="M4.2 2h15.6c.3 1.3.9 2.4 1.8 3.3-.9 2.3-.9 4.6 0 7-.6 5-3.9 8.3-9.6 10.3C6.3 20.6 3 17.3 2.4 12.3c.9-2.4.9-4.7 0-7C3.3 4.4 3.9 3.3 4.2 2z" fill="#fff" stroke="#111" stroke-width="1.3"/>${text("#111", 15.8)}`);
  }
  if (kind === "SR") {
    return wrap(`<path d="M12 1.4c4.4 0 8.2 1 9.6 2.3.5 6.6-1.4 13.6-9.6 19C3.8 17.3 1.9 10.3 2.4 3.7 3.8 2.4 7.6 1.4 12 1.4z" fill="#00713f" stroke="#fff" stroke-width="1"/>${text("#fff", 15.6)}`);
  }
  return wrap(`<rect x="1.8" y="3.6" width="20.4" height="16.8" rx="5.5" fill="#fff" stroke="#111" stroke-width="1.3"/>${text("#111", 15.9)}`);
}

const LAND = [
  [900, [0.68, 0.62, 0.42]], [1500, [0.52, 0.53, 0.34]], [1900, [0.21, 0.37, 0.26]], [2300, [0.27, 0.40, 0.30]],
  [2700, [0.55, 0.53, 0.48]], [3300, [0.70, 0.68, 0.65]],
];
const WATER = [0.16, 0.42, 0.66];
const SNOW = [0.96, 0.975, 1.0];

function landColor(m) {
  if (m <= LAND[0][0]) return LAND[0][1];
  for (let i = 1; i < LAND.length; i++) {
    if (m <= LAND[i][0]) {
      const f = (m - LAND[i - 1][0]) / (LAND[i][0] - LAND[i - 1][0]);
      return LAND[i - 1][1].map((c, k) => c + f * (LAND[i][1][k] - c));
    }
  }
  return LAND[LAND.length - 1][1];
}

// The storm window around "now": back to the last 12-hour dry gap, forward to the next one.
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

export async function createMap(container, data, {onSelect, elevation = "summit", selected = null, globe = false} = {}) {
  const RADIUS = globe ? GLOBE_KM : DISC_KM, TARGET_Z = globe ? 7 : 1;
  const [meta, buffer, roads] = await Promise.all([
    fetch("data/terrain.json").then((r) => r.json()),
    fetch("data/terrain.bin").then((r) => r.arrayBuffer()),
    fetch("data/roads.json").then((r) => r.ok ? r.json() : []).catch(() => []),
  ]);
  const heights = new Uint16Array(buffer);
  const {rows, columns, width_km: W, height_km: H} = meta;
  const zOf = (m) => (Math.max(m, FLOOR_M) - 1897) / 1000 * EXAGGERATION;
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
  const lakeX = xOf(-120.04), lakeY = yOf(39.05);
  const inGlobe = (x, y, margin = 0) => Math.hypot(x - lakeX, y - lakeY) < RADIUS - margin;
  // 1 well inside the disc, falling to 0 at its edge: a hard cut for the globe, a soft fade otherwise.
  const cover = (x, y) => {
    const inside = RADIUS - Math.hypot(x - lakeX, y - lakeY);
    if (globe) return inside > 0 ? 1 : 0;
    const f = Math.min(1, Math.max(0, inside / DISC_FADE_KM));
    return f * f * (3 - 2 * f);
  };
  if (globe) camera.position.set(lakeX - 8, lakeY - 150, 104); else camera.position.set(lakeX - 6, lakeY - 104, 78);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(lakeX, lakeY - (globe ? 0 : 4), TARGET_Z);
  controls.enableDamping = true;
  controls.enablePan = true;
  controls.screenSpacePanning = false;
  controls.minPolarAngle = Math.PI * 0.12;
  controls.maxPolarAngle = Math.PI * 0.40;
  // Panning stays over the terrain and at lake level.
  controls.addEventListener("change", () => {
    const t = controls.target, d = Math.hypot(t.x - lakeX, t.y - lakeY), reach = RADIUS * 0.75;
    const x = d > reach ? lakeX + (t.x - lakeX) * reach / d : t.x, y = d > reach ? lakeY + (t.y - lakeY) * reach / d : t.y;
    if (x !== t.x || y !== t.y || t.z !== TARGET_Z) { camera.position.x += x - t.x; camera.position.y += y - t.y; t.set(x, y, TARGET_Z); }
  });
  controls.minDistance = 40;
  controls.maxDistance = globe ? 260 : 190;
  controls.zoomSpeed = 0.6;
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- gestures: one finger and a plain scroll wheel belong to the page; two fingers move the map ----------
  const canvas = renderer.domElement;
  controls.touches = {ONE: -1, TWO: -1};
  canvas.style.touchAction = "pan-y";
  canvas.addEventListener("wheel", (e) => { if (!e.ctrlKey && !e.metaKey) e.stopImmediatePropagation(); }, {capture: true});
  let lastTouch = 0, gesture = null;
  const UP = new THREE.Vector3(0, 0, 1);
  const twoFingers = (e) => {
    const [a, b] = e.touches;
    return {x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2,
      span: Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY), angle: Math.atan2(b.clientY - a.clientY, b.clientX - a.clientX)};
  };
  canvas.addEventListener("touchstart", (e) => { gesture = e.touches.length === 2 ? twoFingers(e) : null; lastTouch = performance.now(); }, {passive: true});
  canvas.addEventListener("touchend", (e) => { gesture = e.touches.length === 2 ? twoFingers(e) : null; lastTouch = performance.now(); }, {passive: true});
  canvas.addEventListener("touchmove", (e) => {
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
    const idle = !calm && !dragging && !gesture && t - Math.max(lastInput, lastTouch) > IDLE_S * 1000;
    if (!idle) { swayEase = 0; swayClock = 0; return; }
    swayEase = Math.min(1, swayEase + dt / 3);
    const before = Math.sin(2 * Math.PI * swayClock / SWAY_PERIOD_S);
    swayClock += dt;
    const step = (Math.sin(2 * Math.PI * swayClock / SWAY_PERIOD_S) - before) * SWAY_DEG * Math.PI / 180 * swayEase;
    camera.position.sub(controls.target).applyAxisAngle(UP, step).add(controls.target);
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
      water[i] = r > 0 && r < rows - 1 && c > 0 && c < columns - 1 && flat(i - 1) && flat(i + 1) && flat(i - columns) && flat(i + columns) ? 1 : 0;
    }
  }
  const shore = water.slice();
  for (let i = columns; i < count - columns; i++) if (!water[i] && (water[i - 1] || water[i + 1] || water[i - columns] || water[i + columns]) && Math.abs(heights[i] - heights[i - 1]) < 2) shore[i] = 1;
  for (let i = 0; i < count; i++) {
    base.set(shore[i] ? WATER : landColor(heights[i]), 3 * i);
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
  const bins = Math.ceil(3400 / BIN_M);
  const fresh = Array.from({length: steps}, () => new Float32Array(bins));
  for (let i = 1; i < steps; i++) {
    const h = storm.start + i - 1;
    for (let b = 0; b < bins; b++) {
      const above = Math.min(1, Math.max(0, (b * BIN_M - (snowLevel[h] - 100)) / 200));
      fresh[i][b] = fresh[i - 1][b] + rate[h] * above;
    }
  }

  // ---------- roads ----------
  const overlay = document.createElement("div");
  overlay.className = "map-labels";
  container.appendChild(overlay);
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
  const SHIELD_ORDER = ["SR-267", "NV-207", "NV-431", "SR-28", "NV-28", "I-80", "US-50", "SR-89", "SR-88", "US-395", "I-580", "SR-49", "SR-20", "SR-4"];
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
  const ghostMaterial = new THREE.MeshBasicMaterial({color: 0x3987e5, transparent: true, opacity: 0.25, depthWrite: false});
  const fillMaterial = new THREE.MeshStandardMaterial({color: 0x3f8ff0, roughness: 0.4, emissive: 0x16407c, emissiveIntensity: 0.5});
  const pickMaterial = new THREE.MeshStandardMaterial({color: 0xffffff, roughness: 0.4, emissive: 0x3f8ff0, emissiveIntensity: 0.9});
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
    return {key: r.key, name: r.name, x, y, z, ghost, fill, label, n, top: new THREE.Vector3(), width: 80, tall: 40};
  });
  const lake = document.createElement("div");
  lake.className = "map-lake"; lake.textContent = "Lake Tahoe";
  overlay.appendChild(lake);
  const lakeAt = new THREE.Vector3(lakeX, yOf(39.09), zOf(1897) + 0.1);

  // ---------- falling snow (fills the whole view, from well above the peaks) ----------
  const flakePositions = new Float32Array(FLAKES * 3), flakeSpeed = new Float32Array(FLAKES);
  for (let i = 0; i < FLAKES; i++) {
    const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * (globe ? GLOBE_KM - 1.5 : RADIUS * 1.15), x = lakeX + Math.cos(a) * d, y = lakeY + Math.sin(a) * d;
    flakePositions.set([x, y, floorZ + Math.random() * (domeTop(x, y) - floorZ)], 3 * i);
    flakeSpeed[i] = 2.5 + Math.random() * 3.5;
  }
  const flakeGeometry = new THREE.BufferGeometry();
  flakeGeometry.setAttribute("position", new THREE.BufferAttribute(flakePositions, 3));
  const flakeMaterial = new THREE.PointsMaterial({color: 0xffffff, size: 0.5, transparent: true, opacity: 0, depthWrite: false, sizeAttenuation: true});
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
  const show = (v) => v < 0.05 ? "0" : v < 10 ? v.toFixed(1) : String(Math.round(v));

  function paint() {
    const i = Math.min(steps - 1, Math.floor(time)), j = Math.min(steps - 1, i + 1), f = time - i;
    for (let v = 0; v < count; v++) {
      if (shore[v]) continue;
      const b = Math.min(bins - 1, Math.floor(heights[v] / BIN_M));
      const amount = fresh[i][b] + f * (fresh[j][b] - fresh[i][b]);
      const w = Math.min(1, amount / WHITEN_AT_IN), s = w * w * (3 - 2 * w);
      colors[4 * v] = base[3 * v] + s * (SNOW[0] - base[3 * v]);
      colors[4 * v + 1] = base[3 * v + 1] + s * (SNOW[1] - base[3 * v + 1]);
      colors[4 * v + 2] = base[3 * v + 2] + s * (SNOW[2] - base[3 * v + 2]);
    }
    terrain.attributes.color.needsUpdate = true;
    for (const item of items) {
      const all = cumulative[item.n][steps - 1], value = interp(cumulative[item.n], time);
      item.ghost.scale.z = Math.max(0.02, all * STAKE_KM_PER_IN);
      item.fill.scale.z = Math.max(0.02, value * STAKE_KM_PER_IN);
      item.fill.material = item.key === picked ? pickMaterial : fillMaterial;
      const more = all - value;
      item.label.innerHTML = `<b>${item.name}</b><span>${show(value)} in</span>${more >= 0.5 ? `<em>+${show(more)} to come</em>` : ""}`;
      item.label.classList.toggle("on", item.key === picked);
      item.label.title = item.name;
      item.width = 16 + Math.max(item.name.length * 6.6, more >= 0.5 ? 78 : 44);
      item.tall = more >= 0.5 ? 54 : 40;
    }
    flakeMaterial.opacity = Math.min(0.95, interp(rate, time, storm.start) * 3.2);
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
    }).sort((a, b) => (b.item.key === picked) - (a.item.key === picked) || a.p.depth - b.p.depth);
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
      label.style.transform = `translate(-50%, -100%) translate(${p.x.toFixed(1)}px, ${(p.y - 6).toFixed(1)}px)`;
      label.style.zIndex = String(100000 + Math.round((1 - p.depth) * 100000));
    }
    // Whole-pixel positions: at fractional offsets the browser snaps text and shapes differently, so the
    // number wobbles inside its shield as the map moves.
    const put = (element, point, allowed = true) => {
      const p = project(point);
      element.style.display = p.shown && allowed ? "" : "none";
      if (!element._size && element.offsetWidth) element._size = [element.offsetWidth, element.offsetHeight];
      const [width, height] = element._size || [0, 0];
      element.style.transform = `translate(${Math.round(p.x - width / 2)}px, ${Math.round(p.y - height / 2)}px)`;
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
  new ResizeObserver(resize).observe(container);
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }).observe(container);
  resize();

  let last = performance.now();
  function frame(t) {
    if (!running) return;
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (t - last) / 1000); last = t;
    if (!visible) return;
    if (paintedAt !== time) paint();
    if (flakeMaterial.opacity > 0.01 && !calm) {
      for (let i = 0; i < FLAKES; i++) {
        let z = flakePositions[3 * i + 2] - flakeSpeed[i] * dt;
        if (z < 0) z = domeTop(flakePositions[3 * i], flakePositions[3 * i + 1]) - 0.5;
        flakePositions[3 * i + 2] = z;
      }
      flakeGeometry.attributes.position.needsUpdate = true;
    }
    sway(t, dt);
    controls.update();
    renderer.render(scene, camera);
    placeLabels();
  }
  requestAnimationFrame(frame);

  return {
    steps, nowStep, stormActive: storm.active,
    timeAt: (i) => new Date(hoursUtc[storm.start + Math.min(steps - 1, Math.max(0, Math.round(i)))]),
    rateAt: (i) => interp(rate, i, storm.start),
    snowLevelFtAt: (i) => interp(snowLevel, i, storm.start) / 0.3048,
    setTime(value) { time = Math.max(0, Math.min(steps - 1, value)); },
    setElevation(value) { level = value; cumulative = series(); paintedAt = -1; },
    select(key) { picked = key; paintedAt = -1; },
    // controlPoints: [{route, lat, lon, status: "chains" | "closed", name}] from the Caltrans chain-control feed.
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
      for (const point of controlPoints.filter((p) => p.status === "closed")) {
        const x = xOf(point.lon), y = yOf(point.lat);
        if (!inGlobe(x, y, globe ? 1 : DISC_FADE_KM * 0.6)) continue;
        if (closures.some((c) => c.route === point.route && Math.hypot(c.x - x, c.y - y) < 6)) continue;
        const tag = document.createElement("div");
        tag.className = "map-closed"; tag.textContent = "Closed"; tag.title = `${point.route} ${point.name}`;
        overlay.appendChild(tag);
        closures.push({tag, route: point.route, x, y, point: new THREE.Vector3(x, y, zOf(heightAt(point.lat, point.lon)) + 0.9)});
      }
    },
    dispose() { running = false; renderer.dispose(); },
  };
}
