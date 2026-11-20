// 3D map of the Tahoe basin: real terrain, resorts as snow stakes, and a storm you can play forward.
// Scene units are kilometers; x is east, y is north, z is up.
import * as THREE from "three";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";

const EXAGGERATION = 2.7;
const STAKE_KM_PER_IN = 0.16;
const STAKE_RADIUS = 0.7;
const FLAKES = 2600;
const WHITEN_AT_IN = 5;
const BIN_M = 50;
const FLOOR_M = 1200;

const LAND = [
  [1200, [0.66, 0.60, 0.42]], [1500, [0.52, 0.53, 0.34]], [1900, [0.21, 0.37, 0.26]], [2300, [0.27, 0.40, 0.30]],
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

export async function createMap(container, data, {onSelect, elevation = "summit", selected = null} = {}) {
  const [meta, buffer] = await Promise.all([
    fetch("data/terrain.json").then((r) => r.json()),
    fetch("data/terrain.bin").then((r) => r.arrayBuffer()),
  ]);
  const heights = new Uint16Array(buffer);
  const {rows, columns, width_km: W, height_km: H} = meta;
  const zOf = (m) => (Math.max(m, FLOOR_M) - 1897) / 1000 * EXAGGERATION;
  const xOf = (lon) => ((lon - meta.lon_w) / (meta.lon_e - meta.lon_w) - 0.5) * W;
  const yOf = (lat) => ((lat - meta.lat_s) / (meta.lat_n - meta.lat_s) - 0.5) * H;
  const heightAt = (lat, lon) => {
    const r = Math.round((meta.lat_n - lat) / (meta.lat_n - meta.lat_s) * (rows - 1));
    const c = Math.round((lon - meta.lon_w) / (meta.lon_e - meta.lon_w) * (columns - 1));
    return heights[Math.min(rows - 1, Math.max(0, r)) * columns + Math.min(columns - 1, Math.max(0, c))];
  };

  // ---------- scene ----------
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 1, 1000);
  camera.up.set(0, 0, 1);
  camera.position.set(-24, -80, 44);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(3, 4, 1);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.46;
  controls.minDistance = 35;
  controls.maxDistance = 260;
  controls.zoomSpeed = 0.6;
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  controls.autoRotate = !calm;
  controls.autoRotateSpeed = 0.35;
  controls.addEventListener("start", () => { controls.autoRotate = false; });
  scene.add(new THREE.HemisphereLight(0xe8f1fa, 0x6b6253, 1.15));
  const sun = new THREE.DirectionalLight(0xfff4e2, 2.1);
  sun.position.set(-70, 60, 55);
  scene.add(sun);

  // ---------- terrain ----------
  const count = rows * columns;
  const positions = new Float32Array(count * 3), colors = new Float32Array(count * 3), base = new Float32Array(count * 3);
  const water = new Uint8Array(count);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < columns; c++) {
      const i = r * columns + c, m = heights[i];
      positions[3 * i] = (c / (columns - 1) - 0.5) * W;
      positions[3 * i + 1] = (0.5 - r / (rows - 1)) * H;
      positions[3 * i + 2] = zOf(m);
      const flat = (j) => Math.abs(heights[j] - m) < 0.6;
      water[i] = r > 0 && r < rows - 1 && c > 0 && c < columns - 1 && flat(i - 1) && flat(i + 1) && flat(i - columns) && flat(i + columns) ? 1 : 0;
    }
  }
  // Grow water one cell so shorelines read cleanly.
  const shore = water.slice();
  for (let i = columns; i < count - columns; i++) if (!water[i] && (water[i - 1] || water[i + 1] || water[i - columns] || water[i + columns]) && Math.abs(heights[i] - heights[i - 1]) < 2) shore[i] = 1;
  for (let i = 0; i < count; i++) {
    const rgb = shore[i] ? WATER : landColor(heights[i]);
    base.set(rgb, 3 * i);
  }
  colors.set(base);
  const index = new Uint32Array((rows - 1) * (columns - 1) * 6);
  let k = 0;
  for (let r = 0; r < rows - 1; r++) for (let c = 0; c < columns - 1; c++) {
    const a = r * columns + c, b = a + 1, d = a + columns, e = d + 1;
    index.set([a, d, b, b, d, e], k); k += 6;
  }
  const terrain = new THREE.BufferGeometry();
  terrain.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  terrain.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  terrain.setIndex(new THREE.BufferAttribute(index, 1));
  terrain.computeVertexNormals();
  scene.add(new THREE.Mesh(terrain, new THREE.MeshStandardMaterial({vertexColors: true, roughness: 0.92, metalness: 0})));

  // Side walls so the block reads as a solid slab.
  const floor = zOf(FLOOR_M) - 0.5;
  const wallMaterial = new THREE.MeshStandardMaterial({color: 0x4a4f55, roughness: 1, side: THREE.DoubleSide});
  const wall = (indices) => {
    const p = new Float32Array(indices.length * 6), idx = [];
    indices.forEach((i, n) => {
      p.set([positions[3 * i], positions[3 * i + 1], positions[3 * i + 2], positions[3 * i], positions[3 * i + 1], floor], n * 6);
      if (n) idx.push(2 * n - 2, 2 * n - 1, 2 * n, 2 * n, 2 * n - 1, 2 * n + 1);
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(p, 3));
    g.setIndex(idx); g.computeVertexNormals();
    scene.add(new THREE.Mesh(g, wallMaterial));
  };
  const seq = (n, f) => Array.from({length: n}, (_, i) => f(i));
  wall(seq(columns, (c) => c)); wall(seq(columns, (c) => (rows - 1) * columns + c));
  wall(seq(rows, (r) => r * columns)); wall(seq(rows, (r) => r * columns + columns - 1));

  // ---------- forecast series ----------
  const now = new Date(data.generated_utc).getTime();
  const hoursUtc = data.resorts[0].hours_utc;
  const first = Math.max(0, hoursUtc.findIndex((t) => new Date(t).getTime() >= now));
  const steps = Math.min(hoursUtc.length - first, 24 * 5 + 1);
  let level = elevation;
  const series = () => data.resorts.map((r) => {
    const h = r.elevations[level].hourly, cum = new Float32Array(steps);
    for (let i = 1; i < steps; i++) cum[i] = cum[i - 1] + (h.snow_in[first + i - 1] || 0);
    return cum;
  });
  let cumulative = series();
  // Region-wide snowfall rate and snow level, from the summit forecasts.
  const rate = new Float32Array(steps), snowLevel = new Float32Array(steps);
  for (let i = 0; i < steps; i++) {
    let sum = 0, lv = 0, n = 0;
    for (const r of data.resorts) {
      const h = r.elevations.summit.hourly;
      sum += h.snow_in[first + i] || 0;
      if (h.snow_level_ft[first + i] != null) { lv += h.snow_level_ft[first + i] * 0.3048; n++; }
    }
    rate[i] = sum / data.resorts.length; snowLevel[i] = n ? lv / n : 9999;
  }
  // Fresh snow by elevation band: each hour's snowfall lands on everything above that hour's snow level.
  const bins = Math.ceil(3400 / BIN_M);
  const fresh = seq(steps, () => new Float32Array(bins));
  for (let i = 1; i < steps; i++) {
    for (let b = 0; b < bins; b++) {
      const above = Math.min(1, Math.max(0, (b * BIN_M - (snowLevel[i - 1] - 100)) / 200));
      fresh[i][b] = fresh[i - 1][b] + rate[i - 1] * above;
    }
  }

  // ---------- resorts ----------
  const stakes = new THREE.Group();
  scene.add(stakes);
  const labels = document.createElement("div");
  labels.className = "map-labels";
  container.appendChild(labels);
  const ghostMaterial = new THREE.MeshBasicMaterial({color: 0x3987e5, transparent: true, opacity: 0.22, depthWrite: false});
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
    labels.appendChild(label);
    return {key: r.key, name: r.name, x, y, z, ghost, fill, label, n, top: new THREE.Vector3()};
  });
  const lake = document.createElement("div");
  lake.className = "map-lake"; lake.textContent = "Lake Tahoe";
  labels.appendChild(lake);
  const lakeAt = new THREE.Vector3(xOf(-120.03), yOf(39.09), zOf(1897) + 0.1);

  // ---------- falling snow ----------
  const flakePositions = new Float32Array(FLAKES * 3), flakeSpeed = new Float32Array(FLAKES);
  const ceiling = zOf(3300) + 9;
  for (let i = 0; i < FLAKES; i++) {
    flakePositions.set([(Math.random() - 0.5) * W, (Math.random() - 0.5) * H, Math.random() * ceiling], 3 * i);
    flakeSpeed[i] = 2.5 + Math.random() * 3;
  }
  const flakeGeometry = new THREE.BufferGeometry();
  flakeGeometry.setAttribute("position", new THREE.BufferAttribute(flakePositions, 3));
  const flakeMaterial = new THREE.PointsMaterial({color: 0xffffff, size: 0.55, transparent: true, opacity: 0, depthWrite: false, sizeAttenuation: true});
  const flakes = new THREE.Points(flakeGeometry, flakeMaterial);
  scene.add(flakes);

  // ---------- state ----------
  let time = 0, paintedAt = -1, picked = selected, visible = true, running = true;
  const interp = (array, t) => {
    const i = Math.min(steps - 1, Math.floor(t)), j = Math.min(steps - 1, i + 1), f = t - i;
    return array[i] + f * (array[j] - array[i]);
  };

  function paint() {
    const i = Math.min(steps - 1, Math.floor(time)), j = Math.min(steps - 1, i + 1), f = time - i;
    for (let v = 0; v < count; v++) {
      if (shore[v]) continue;
      const b = Math.min(bins - 1, Math.floor(heights[v] / BIN_M));
      const amount = fresh[i][b] + f * (fresh[j][b] - fresh[i][b]);
      const w = Math.min(1, amount / WHITEN_AT_IN), s = w * w * (3 - 2 * w);
      colors[3 * v] = base[3 * v] + s * (SNOW[0] - base[3 * v]);
      colors[3 * v + 1] = base[3 * v + 1] + s * (SNOW[1] - base[3 * v + 1]);
      colors[3 * v + 2] = base[3 * v + 2] + s * (SNOW[2] - base[3 * v + 2]);
    }
    terrain.attributes.color.needsUpdate = true;
    for (const item of items) {
      const total = cumulative[item.n][steps - 1], value = interp(cumulative[item.n], time);
      item.ghost.scale.z = Math.max(0.02, total * STAKE_KM_PER_IN);
      item.fill.scale.z = Math.max(0.02, value * STAKE_KM_PER_IN);
      item.fill.material = item.key === picked ? pickMaterial : fillMaterial;
      item.value = value;
      item.label.innerHTML = `<b>${item.name}</b><span>${value < 0.05 ? "0" : value < 10 ? value.toFixed(1) : Math.round(value)} in</span>`;
      item.label.classList.toggle("on", item.key === picked);
      item.label.title = item.name;
      item.width = 16 + Math.max(item.name.length * 6.6, 44);
    }
    flakeMaterial.opacity = Math.min(0.95, interp(rate, time) * 3.2);
    paintedAt = time;
  }

  function placeLabels() {
    const w = container.clientWidth, h = container.clientHeight;
    const project = (point) => {
      const p = point.clone().project(camera);
      return {x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, depth: p.z, shown: p.z < 1 && Math.abs(p.x) < 1.05 && Math.abs(p.y) < 1.05};
    };
    // Nearest labels are placed first; one that would cover another shrinks to just its number, then steps upward.
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
      let mini = false, lift = 0, rect = box(item.width, 40, 0);
      if (hits(rect)) { mini = true; rect = box(46, 24, 0); }
      while (hits(rect) && lift < 78) { lift += 26; rect = box(46, 24, lift); }
      placed.push(rect);
      label.classList.toggle("mini", mini);
      label.style.transform = `translate(-50%, -100%) translate(${p.x.toFixed(1)}px, ${(p.y - 6 - lift).toFixed(1)}px)`;
      label.style.zIndex = String(Math.round((1 - p.depth) * 100000));
    }
    const lp = project(lakeAt);
    lake.style.display = lp.shown ? "" : "none";
    lake.style.transform = `translate(-50%, -50%) translate(${lp.x.toFixed(1)}px, ${lp.y.toFixed(1)}px)`;
  }

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // Pull back on narrow screens so the whole basin stays in view.
    camera.fov = w < 520 ? 44 : 32;
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
    steps,
    timeAt: (i) => new Date(hoursUtc[first + Math.min(steps - 1, Math.round(i))]),
    rateAt: (i) => interp(rate, i),
    snowLevelFtAt: (i) => interp(snowLevel, i) / 0.3048,
    setTime(value) { time = Math.max(0, Math.min(steps - 1, value)); },
    setElevation(value) { level = value; cumulative = series(); paintedAt = -1; },
    select(key) { picked = key; paintedAt = -1; },
    dispose() { running = false; renderer.dispose(); },
  };
}
