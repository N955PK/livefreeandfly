// 3D map of the Tahoe basin: real terrain, resorts as snow stakes for the current storm, and live road status.
// Scene units are kilometers; x is east, y is north, z is up.
import * as THREE from "three";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";

const EXAGGERATION = 2.7;
const STAKE_KM_PER_IN = 0.16;
const STAKE_RADIUS = 0.7;
const FLAKES = 3200;
const WHITEN_AT_IN = 5;
const BIN_M = 50;
const FLOOR_M = 900;
const EDGE_FADE_KM = 16;
const DRY_GAP_H = 12;
const DRY_RATE = 0.01;
const MAX_AHEAD_H = 96;
const ROAD_LIFT = 0.16;
const ROAD_COLORS = {open: [0.20, 0.23, 0.27], chains: [0.96, 0.66, 0.05], closed: [0.84, 0.18, 0.18]};
const MAJOR = new Set(["I-80", "US-50", "US-395", "I-580"]);

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

export async function createMap(container, data, {onSelect, elevation = "summit", selected = null} = {}) {
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
  camera.position.set(lakeX - 6, lakeY - 112, 84);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(lakeX - 3, lakeY - 4, 1);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minPolarAngle = Math.PI * 0.12;
  controls.maxPolarAngle = Math.PI * 0.40;
  controls.minAzimuthAngle = -Math.PI * 0.3;
  controls.maxAzimuthAngle = Math.PI * 0.3;
  controls.minDistance = 45;
  controls.maxDistance = 190;
  controls.zoomSpeed = 0.6;
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
      const edge = Math.min(W / 2 - Math.abs(x), H / 2 - Math.abs(y)) / EDGE_FADE_KM;
      const fade = Math.min(1, Math.max(0, edge));
      colors[4 * i + 3] = fade * fade * (3 - 2 * fade);
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
  scene.add(new THREE.Mesh(terrain, new THREE.MeshStandardMaterial({vertexColors: true, transparent: true, roughness: 0.92, metalness: 0})));

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
  const shields = [];
  for (const road of roads) {
    const half = (MAJOR.has(road.route) ? 0.42 : 0.3);
    let longest = null;
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
      if (!longest || pts.length > longest.length) longest = pts;
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
    if (longest && longest.length > 8) {
      const [lon, lat] = longest[Math.floor(longest.length * 0.5)];
      const tag = document.createElement("div");
      tag.className = "map-shield"; tag.textContent = road.route.replace(/^[A-Z]+-/, "");
      overlay.appendChild(tag);
      shields.push({tag, point: new THREE.Vector3(xOf(lon), yOf(lat), zOf(heightAt(lat, lon)) + 0.5), inside: Math.abs(xOf(lon)) < W / 2 - EDGE_FADE_KM && Math.abs(yOf(lat)) < H / 2 - EDGE_FADE_KM});
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
      const fade = Math.min(1, Math.max(0, Math.min(W / 2 - Math.abs(x), H / 2 - Math.abs(y)) / EDGE_FADE_KM));
      roadColors.set([...rgb, fade, ...rgb, fade], 8 * i);
    });
    roadGeometry.attributes.color.needsUpdate = true;
  };
  paintRoads(() => "open");
  scene.add(new THREE.Mesh(roadGeometry, new THREE.MeshBasicMaterial({vertexColors: true, transparent: true, side: THREE.DoubleSide, depthWrite: false})));
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
  const ceiling = 38, spreadX = W * 0.75, spreadY = H * 0.75;
  for (let i = 0; i < FLAKES; i++) {
    flakePositions.set([lakeX + (Math.random() - 0.5) * spreadX, lakeY + (Math.random() - 0.5) * spreadY, Math.random() * ceiling], 3 * i);
    flakeSpeed[i] = 3 + Math.random() * 4;
  }
  const flakeGeometry = new THREE.BufferGeometry();
  flakeGeometry.setAttribute("position", new THREE.BufferAttribute(flakePositions, 3));
  const flakeMaterial = new THREE.PointsMaterial({color: 0xffffff, size: 0.5, transparent: true, opacity: 0, depthWrite: false, sizeAttenuation: true});
  scene.add(new THREE.Points(flakeGeometry, flakeMaterial));

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
      let mini = false, lift = 0, rect = box(item.width, item.tall, 0);
      if (hits(rect)) { mini = true; rect = box(46, 24, 0); }
      while (hits(rect) && lift < 78) { lift += 26; rect = box(46, 24, lift); }
      placed.push(rect);
      label.classList.toggle("mini", mini);
      label.style.transform = `translate(-50%, -100%) translate(${p.x.toFixed(1)}px, ${(p.y - 6 - lift).toFixed(1)}px)`;
      label.style.zIndex = String(100000 + Math.round((1 - p.depth) * 100000));
    }
    const put = (element, point, allowed = true) => {
      const p = project(point);
      element.style.display = p.shown && allowed ? "" : "none";
      element.style.transform = `translate(-50%, -50%) translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px)`;
    };
    put(lake, lakeAt);
    for (const shield of shields) put(shield.tag, shield.point, shield.inside);
    for (const closure of closures) put(closure.tag, closure.point);
  }

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // Widen the lens on narrow screens so the whole lake stays in view.
    camera.fov = w < 520 ? 48 : 30;
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
        if (z < 0) z = ceiling;
        flakePositions[3 * i + 2] = z;
        flakePositions[3 * i] += Math.sin(t / 900 + i) * dt * 0.6;
      }
      flakeGeometry.attributes.position.needsUpdate = true;
    }
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
        if (Math.abs(x) > W / 2 - EDGE_FADE_KM / 2 || Math.abs(y) > H / 2 - EDGE_FADE_KM / 2) continue;
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
