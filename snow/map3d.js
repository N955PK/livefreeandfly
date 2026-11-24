// 3D map of one region: real terrain, resorts and peaks as snow stakes for the current storm, live road status,
// and the avalanche danger rating as an optional tint.
// Scene units are kilometers; x is east, y is north, z is up.
import * as THREE from "three";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";

const EXAGGERATION = 2.7;
const STAKE_KM_PER_IN = 0.16;
const STAKE_RADIUS = 0.7;
// A stake comes to a point under its body, this many of its radii long, and floats this far over the highest ground
// within its reach, so its tip marks the spot without sinking into the slope.
const STAKE_TIP_RADII = 2.2;
const STAKE_GAP_KM = 0.3;
// The closest a part of a region is framed, in km from the camera to the point it looks at, when it takes a view
// closer than Tahoe's opening to show every mountain's name: closer than this the terrain's cells show as facets.
const CLOSEST_KM = 50;
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

// ``plainState`` draws an "SR" route with the plain marker: Washington writes its state routes "SR" too.
function shieldSVG(route, plainState = false) {
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
  if (kind === "SR" && !plainState) {
    return wrap("-12 -4 409 409", `<path d="${CA_SPADE}" fill="#fff"/>
      <path d="${CA_SPADE}" fill="#006b54" transform="translate(192.5 215) scale(.92) translate(-192.5 -215)"/>
      ${text("#fff", 192.5, long ? 330 : 340, long ? 155 : 200)}`);
  }
  if (kind === "NV") {
    return wrap("0 0 600 600", `<rect width="600" height="600" rx="70" fill="#111"/><path d="${NEVADA}" fill="#fff"/>
      ${text("#111", 300, long ? 250 : 270, long ? 172 : 230)}`);
  }
  // Any other state's route: the plain black-on-white marker most states use.
  return wrap("-12 -12 624 624", `<rect x="40" y="90" width="520" height="420" rx="40" fill="#fff" stroke="#111" stroke-width="30"/>
    ${text("#111", 300, long ? 375 : 395, long ? 220 : 290)}`);
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

// The water of a region with a mask: each point of the land takes the water's color where the water's share,
// read smoothly between the cells, is over one half, so the shore follows that line rather than the cells' edges.
// It is softened over about the width Lake Tahoe's shore blends across, and lit as the land and the lakes are.
const SHORE_SOFT = 0.12;
function wetShore(material) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.waterColor = {value: new THREE.Vector3(...WATER)};
    shader.vertexShader = shader.vertexShader.replace("#include <common>", "#include <common>\nattribute float wet;\nvarying float vWet;")
      .replace("#include <color_vertex>", "#include <color_vertex>\nvWet = wet;");
    shader.fragmentShader = shader.fragmentShader.replace("#include <common>", "#include <common>\nvarying float vWet;\nuniform vec3 waterColor;")
      .replace("#include <color_fragment>", `#include <color_fragment>
        float soft = max(fwidth(vWet) * 0.75, ${SHORE_SOFT.toFixed(2)});
        diffuseColor.rgb = mix(diffuseColor.rgb, waterColor, smoothstep(0.5 - soft, 0.5 + soft, vWet));`);
  };
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

// ---------- where the names sit ----------
// A name sits over its stake, centred, or to one side ("e": it runs east of the stake from its pointer, "w": west),
// with its pointer TAIL_IN px in from that end, so it still plainly marks its own stake; and it is full, or shrunk to
// its number. ``list`` is [{item: {key, width, tall}, x, y}] in the order they claim room (the selected first, then
// the nearest), x and y the point the pointer touches. Each takes the first spot clear of those before it: centred,
// then the side toward the middle of the screen, then the other, then the same shrunk. One that finds none may move
// an earlier neighbour to its far side to make room, so two close names stand back to back. One that still finds none
// is hidden. ``was`` (key to the spot it had) keeps a name on its side until centred is clear by a margin, so it does
// not flip back and forth as the view moves. Returns [{item, spot: [side, mini], box}] for the names that show.
const TAIL_IN = 22, SETTLE_PX = 10;
function layoutLabels(list, width, was = null) {
  const placed = [];
  const boxOf = (p, [side, mini], grow = 0) => {
    const wide = mini ? 46 : p.item.width, tall = mini ? 24 : p.item.tall, inset = Math.min(TAIL_IN, wide / 2);
    const x0 = side === "c" ? p.x - wide / 2 : side === "e" ? p.x - inset : p.x + inset - wide;
    return {x0: x0 - 2 - grow, x1: x0 + wide + 2 + grow, y0: p.y - tall - 6 - grow, y1: p.y + grow};
  };
  const clear = (box, skip) => !placed.some((q) => q !== skip && box.x0 < q.box.x1 && box.x1 > q.box.x0 && box.y0 < q.box.y1 && box.y1 > q.box.y0);
  // A name moved to a side must stay on the screen.
  const fits = (p, spot, grow) => { const box = boxOf(p, spot, grow); return clear(box) && (spot[0] === "c" || (box.x0 >= 0 && box.x1 <= width)); };
  const spotsFor = (p) => {
    const [near, far] = p.x > width / 2 ? ["w", "e"] : ["e", "w"];
    return [["c", false], [near, false], [far, false], ["c", true], [near, true], [far, true]];
  };
  for (const p of list) {
    let spots = spotsFor(p);
    const prev = was && was.get(p.item.key);
    if (prev && prev[0] !== "c") {
      const centred = [["c", prev[1]]].filter((s) => fits(p, s, SETTLE_PX));
      spots = [...centred, prev, ...spots.filter((s) => s[0] !== prev[0] || s[1] !== prev[1])];
    }
    let spot = spots.find((s) => fits(p, s));
    if (!spot) {
      // Make room: a neighbour this name runs into steps to its far side, if that leaves it clear too.
      const mine = boxOf(p, ["c", false]);
      for (const q of placed.filter((q) => q.spot[0] === "c" && mine.x0 < q.box.x1 && mine.x1 > q.box.x0 && mine.y0 < q.box.y1 && mine.y1 > q.box.y0)) {
        const away = [p.x > q.p.x ? "w" : "e", q.spot[1]], moved = boxOf(q.p, away), keep = q.box;
        if (!clear(moved, q) || moved.x0 < 0 || moved.x1 > width) continue;
        q.box = moved;
        spot = spots.filter((s) => s[0] !== "c").find((s) => fits(p, s));
        if (spot) { q.spot = away; break; }
        q.box = keep;
      }
    }
    if (spot) placed.push({item: p.item, p, spot, box: boxOf(p, spot)});
  }
  return placed;
}

// ``region`` says where the map is: {terrain, roads} data files, the disc's center [lat, lon], waterM (the level
// heights are drawn from), and optionally lake: {name, lat, lon} (the water named on the map; no name when absent),
// land (its own colors by elevation), zoom (how close the view opens; 1 when absent), discKm (the disc's radius),
// look ([lat, lon] the view opens on when that is not the disc's center), floorM (ground below this height is drawn at
// it; FLOOR_M when absent), lowlandM (level ground below this height is not taken for a lake; LOWLAND_M when absent)
// and plainStateRoutes (its "SR" routes are not California's, so they get the plain marker, not the spade).
// A missing road file means no road lines.
// ``data.resorts`` holds only that region's locations.
// Below this many inches an hour, averaged over the region, it is not snowing: no flakes on the map, and the page says so.
const QUIET_RATE = 0.02;
export async function createMap(container, data, {region, onSelect, elevation = "summit", selected = null, globe = false, depth = {per: 1, unit: "in"}, freeTouch = () => false, finger = () => "spin", area = null, framePad = () => ({top: 12, right: 12, bottom: 12, left: 12})}) {
  const RADIUS = globe ? GLOBE_KM : region.discKm || DISC_KM, TARGET_Z = globe ? 7 : 1;
  // A region whose files were rebuilt carries a rev, so a phone never pairs the new page with its saved old files.
  const rev = region.rev || "";
  const [meta, buffer, roads] = await Promise.all([
    fetch(`${region.terrain}.json${rev}`).then((r) => r.json()),
    fetch(`${region.terrain}.bin${rev}`).then((r) => r.arrayBuffer()),
    fetch(region.roads + rev).then((r) => r.ok ? r.json() : []).catch(() => []),
  ]);
  const heights = new Uint16Array(buffer);
  // A region built with a water mask (how much of each cell is water, 0 to 255, in runs of a value byte and a
  // count seven bits to a byte, low bits first) draws its water from that, not from the heights.
  const runs = meta.water_mask ? new Uint8Array(await fetch(`${region.terrain}.water.bin${rev}`).then((r) => r.arrayBuffer())) : null;
  const {rows, columns, width_km: W, height_km: H} = meta;
  const floorM = region.floorM ?? FLOOR_M, lowlandM = region.lowlandM ?? LOWLAND_M;
  const zOf = (m) => (Math.max(m, floorM) - region.waterM) / 1000 * EXAGGERATION;
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
  // A disc wider than the terrain also fades out at the terrain's own edges.
  const spills = !globe && RADIUS > Math.min(W, H) / 2;
  const cover = (x, y) => {
    const inside = RADIUS - Math.hypot(x - lakeX, y - lakeY);
    if (globe) return inside > 0 ? 1 : 0;
    const f = Math.min(1, Math.max(0, inside / DISC_FADE_KM)), disc = f * f * (3 - 2 * f);
    if (!spills) return disc;
    const e = Math.min(1, Math.max(0, Math.min(W / 2 - Math.abs(x), H / 2 - Math.abs(y)) / EDGE_FADE_KM));
    return disc * e * e * (3 - 2 * e);
  };
  // A region whose mountains sit close together opens closer in (zoom under 1).
  const zoom = region.zoom || 1;
  // A view that opens further out than Tahoe's draws roads, stakes and the spacing of shields that much larger, so
  // they read the same.
  const sizeUp = globe ? 1 : Math.max(1, zoom);
  if (globe) camera.position.set(lakeX - 8, lakeY - 150, 104); else {
    // The camera starts south of the target; a region can swing it around (45 looks from the southeast).
    const turn = (region.turnDeg || 0) * Math.PI / 180, dx = -6 * zoom, dy = -100 * zoom;
    camera.position.set(lookX + dx * Math.cos(turn) - dy * Math.sin(turn), lookY - 4 + dx * Math.sin(turn) + dy * Math.cos(turn), 1 + 77 * zoom);
  }
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(lookX, lookY - (globe ? 0 : 4), TARGET_Z);
  // The opening view, which "All" of a region with parts returns to.
  const openTarget = controls.target.clone(), openPosition = camera.position.clone(), openR = openPosition.distanceTo(openTarget);
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
  // A region whose mountains spread wider than its disc lets the view open further out (Seattle's); it can still be
  // zoomed out to where it opened.
  controls.maxDistance = globe ? 260 : Math.max(190 * RADIUS / DISC_KM, camera.position.distanceTo(controls.target));
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
  const TILT_MIN = controls.minPolarAngle, TILT_MAX = controls.maxPolarAngle, HOME_POLAR = pose().polar, HOME_TURN = pose().turn, FLAT_POLAR = 0.02, GLIDE_MS = 450;
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
  // A flight also moves the point looked at and the distance (the distance by equal ratios, so a long zoom does not
  // rush its last part), with the same easing and length as a glide. It ends exactly on its goal's position if it has one.
  const flyTo = (to) => {
    const from = {...pose(), target: controls.target.clone()};
    let swing = to.turn - from.turn;
    swing -= 2 * Math.PI * Math.round(swing / (2 * Math.PI));
    const goal = {...to, turn: from.turn + swing};
    controls.minPolarAngle = 0; controls.maxPolarAngle = TILT_MAX;
    glide = {from, goal, began: performance.now(), fly: true};
    if (calm) stepGlide(Infinity);
  };
  const stepGlide = (t) => {
    if (!glide) return;
    const f = Math.min(1, (t - glide.began) / GLIDE_MS), e = f * f * (3 - 2 * f), {from, goal} = glide;
    if (glide.fly) controls.target.lerpVectors(from.target, goal.target, e);
    setPose({r: glide.fly ? from.r * (goal.r / from.r) ** e : pose().r, polar: from.polar + (goal.polar - from.polar) * e, turn: from.turn + (goal.turn - from.turn) * e});
    if (f >= 1) { if (glide.fly && goal.position) camera.position.copy(goal.position); glide = null; settle(); }
  };
  scene.add(new THREE.HemisphereLight(0xe8f1fa, 0x6b6253, 1.15));
  const sun = new THREE.DirectionalLight(0xfff4e2, 2.1);
  sun.position.set(-70, 60, 55);
  scene.add(sun);

  // ---------- terrain (fades out toward its edges, so there is no hard rim) ----------
  const count = rows * columns;
  const positions = new Float32Array(count * 3), colors = new Float32Array(count * 4), base = new Float32Array(count * 3);
  const water = new Uint8Array(count);
  const wet = runs ? new Float32Array(count) : null;
  for (let k = 0, at = 0; runs && k < runs.length;) {
    const value = runs[k++] / 255;
    let n = 0, shift = 0, byte;
    do { byte = runs[k++]; n += (byte & 0x7f) * 2 ** shift; shift += 7; } while (byte & 0x80);
    wet.fill(value, at, at + n); at += n;
  }
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < columns; c++) {
      const i = r * columns + c, m = heights[i];
      const x = (c / (columns - 1) - 0.5) * W, y = (0.5 - r / (rows - 1)) * H;
      positions.set([x, y, zOf(m)], 3 * i);
      colors[4 * i + 3] = cover(x, y);
      const flat = (j) => Math.abs(heights[j] - m) < 0.6;
      // Level ground is a lake in the mountains, but in the Central Valley it is only farmland.
      water[i] = wet ? (wet[i] >= 0.5 ? 1 : 0) : m >= lowlandM && r > 0 && r < rows - 1 && c > 0 && c < columns - 1 && flat(i - 1) && flat(i + 1) && flat(i - columns) && flat(i + columns) ? 1 : 0;
    }
  }
  const shore = water.slice();
  // With a mask the shore is drawn where the water's share crosses one half, between the cells (see wetShore below).
  if (!wet) for (let i = columns; i < count - columns; i++) if (!water[i] && (water[i - 1] || water[i + 1] || water[i - columns] || water[i + columns]) && Math.abs(heights[i] - heights[i - 1]) < 2) shore[i] = 1;
  for (let i = 0; i < count; i++) {
    base.set(shore[i] && !wet ? WATER : landColor(heights[i], region.land || LAND), 3 * i);
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
  if (wet) terrain.setAttribute("wet", new THREE.BufferAttribute(wet, 1));
  terrain.setIndex(new THREE.BufferAttribute(index, 1));
  terrain.computeVertexNormals();
  const ground = new THREE.Mesh(terrain, new THREE.MeshStandardMaterial({vertexColors: true, roughness: 0.92, metalness: 0, ...(globe ? {alphaTest: 0.5} : {transparent: true})}));
  // The same land with no light on it (every slope the same tone), for when the radar is showing.
  const litMaterial = ground.material, flatMaterial = new THREE.MeshBasicMaterial({vertexColors: true, ...(globe ? {alphaTest: 0.5} : {transparent: true})});
  if (wet) { wetShore(litMaterial); wetShore(flatMaterial); }
  ground.renderOrder = 1;
  scene.add(ground);

  // ---------- the globe: a rim wall where the terrain is cut, a base, and a glass dome ----------
  const floorZ = zOf(floorM) - 0.8, SEGMENTS = 360;
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
  // Where the region has no sensor reading at all (New England), the same reckoning is made from the depths the
  // resorts report, each at the elevation it is given for, once they arrive (setReportedGround). Only a sensor's
  // current depth (observed.depth_in) counts as a sensor reading: a dated daily record (observed.daily, the
  // Mt. Washington summit's) takes no part.
  // A resort's depth is mostly snow it made and groomed on its trails, with the woods beside them often bare, so a
  // reported depth counts for half a sensor's, and the snow line is put no lower than the lowest place reporting snow.
  const REPORTED_COUNTS = 0.5;
  const pack = new Float32Array(bins);
  function packFrom(all, reported = false) {
    pack.fill(0);
    const snowy = all.filter(([, d]) => d >= 1).map(([ft, d]) => [ft, reported ? d * REPORTED_COUNTS : d]), bare = all.filter(([, d]) => d < 1);
    if (snowy.length) {
      const mean = (k) => snowy.reduce((sum, p) => sum + p[k], 0) / snowy.length;
      const low = snowy.reduce((a, p) => p[0] < a[0] ? p : a);
      const under = bare.filter(([ft]) => ft < low[0]).map(([ft]) => ft);
      const line = under.length ? Math.max(...under) : reported ? low[0] : low[0] - Math.min(1500, low[1] * 50);
      const ft = Math.max(mean(0), line + 500), deep = mean(1);
      for (let b = 0; b < bins; b++) pack[b] = Math.min(2 * deep, Math.max(0, deep * (b * BIN_M / 0.3048 - line) / (ft - line)));
    }
  }
  const sensed = new Map();
  for (const r of data.resorts) {
    const o = r.observed;
    if (o && o.depth_in != null && o.elevation_ft != null) sensed.set(o.station, [o.elevation_ft, o.depth_in]);
  }
  packFrom([...sensed.values()]);

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
  const roadPositions = [], roadIndex = [], roadSides = [];
  const roadLines = [];
  for (const road of roads) {
    const half = (MAJOR.has(road.route) || road.route.startsWith("I-") ? 0.42 : 0.3) * sizeUp, halfBase = half / sizeUp;
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
        if (sizeUp > 1) roadSides.push(-dy * halfBase, dx * halfBase, dy * halfBase, -dx * halfBase);
        roadPoints.push({route: road.route, lon, lat});
        if (i) { const a = startVertex + 2 * (i - 1); roadIndex.push(a, a + 1, a + 2, a + 2, a + 1, a + 3); }
      });
    }
  }

  // Route shields in their real shapes, spaced along each road and kept clear of the resorts and each other.
  // Short routes go first so they keep a spot.
  const SHIELD_ORDER = ["SR-203", "SR-158", "SR-267", "NV-207", "NV-431", "SR-28", "NV-28", "SR-167", "SR-270", "SR-182", "I-80", "US-50", "SR-89", "SR-88",
    "US-395", "I-580", "SR-49", "SR-20", "SR-4", "SR-120", "SR-108", "SR-168", "US-6"];
  // Routes not named in the order (another region's) follow it, the shortest first.
  const routeLength = (route) => roadLines.filter((line) => line.route === route).reduce((sum, line) => sum + line.pts.length, 0);
  const others = [...new Set(roadLines.map((line) => line.route))].filter((route) => !SHIELD_ORDER.includes(route)).sort((a, b) => routeLength(a) - routeLength(b));
  // The shields are spaced for a scale (``spread``, the size-up they are drawn at). A region that opens further out than
  // Tahoe's gets one set per scale from Tahoe's to its own, and shows the set nearest the scale on screen, so closer in
  // the shields come closer together, as they would on a map that opened there.
  const placeShields = (spread) => {
  const shields = [], placedShields = [];
  for (const route of [...SHIELD_ORDER, ...others]) {
    for (const pts of roadLines.filter((line) => line.route === route).map((line) => line.pts).sort((a, b) => b.length - a.length)) {
      const step = Math.round(SHIELD_EVERY_KM * spread / 0.6);
      // A short road gets one shield, at the first spot that is free.
      const short = pts.length < step;
      const picks = short ? (pts.length > 8 ? [0.5, 0.35, 0.65, 0.2, 0.8].map((f) => Math.floor(pts.length * f)) : [])
        : Array.from({length: Math.floor(pts.length / step)}, (_, n) => Math.floor(step / 2) + n * step);
      let placedHere = 0;
      for (const index of picks) {
        if (short && placedHere) break;
        const [lon, lat] = pts[index], x = xOf(lon), y = yOf(lat);
        if (cover(x, y) < 0.95) continue;
        if (placedShields.some((q) => Math.hypot(q.x - x, q.y - y) < (q.route === route ? 18 * spread : short ? 3.5 : 5))) continue;
        if (data.resorts.some((r) => Math.hypot(xOf(r.lon) - x, yOf(r.lat) - y) < 2.2)) continue;
        const tag = document.createElement("div");
        tag.className = "map-shield"; tag.innerHTML = shieldSVG(route, region.plainStateRoutes); tag.title = route;
        overlay.appendChild(tag);
        placedShields.push({route, x, y});
        placedHere++;
        shields.push({tag, point: new THREE.Vector3(x, y, zOf(heightAt(lat, lon)) + 0.5), inside: true});
      }
    }
  }
  return shields;
  };
  const shieldSpreads = sizeUp > 1 ? [1, Math.sqrt(sizeUp), sizeUp] : [sizeUp];
  const shieldSets = shieldSpreads.map(placeShields);
  let shields = shieldSets[shieldSets.length - 1];
  for (const set of shieldSets) if (set !== shields) for (const shield of set) shield.tag.style.display = "none";
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
  // A region drawn larger than Tahoe's narrows its ribbons as the view comes closer (see scaleTo): each edge moves
  // along its own sideways step by roadWiden (0 at the opening scale, so the opening view is drawn as it was built).
  const roadWiden = {value: 0};
  if (sizeUp > 1) {
    roadGeometry.setAttribute("side", new THREE.Float32BufferAttribute(roadSides, 2));
    ribbons.material.onBeforeCompile = (shader) => {
      shader.uniforms.roadWiden = roadWiden;
      shader.vertexShader = shader.vertexShader.replace("#include <common>", "#include <common>\nattribute vec2 side;\nuniform float roadWiden;")
        .replace("#include <begin_vertex>", "#include <begin_vertex>\ntransformed.xy += side * roadWiden;");
    };
  }
  ribbons.renderOrder = 2;
  scene.add(ribbons);
  const closures = [];

  // ---------- resorts ----------
  const stakes = new THREE.Group();
  scene.add(stakes);
  const ghostMaterial = new THREE.MeshBasicMaterial({color: 0x2a78d6, transparent: true, opacity: 0.25, depthWrite: false});
  const fillMaterial = new THREE.MeshStandardMaterial({color: 0x2a78d6, roughness: 0.4, emissive: 0x0d366b, emissiveIntensity: 0.5});
  const pickMaterial = new THREE.MeshStandardMaterial({color: 0xffffff, roughness: 0.4, emissive: 0x2a78d6, emissiveIntensity: 0.9});
  const unit = new THREE.CylinderGeometry(STAKE_RADIUS * sizeUp, STAKE_RADIUS * sizeUp, 1, 20).rotateX(Math.PI / 2).translate(0, 0, 0.5);
  const tipLength = STAKE_RADIUS * STAKE_TIP_RADII * sizeUp, gap = STAKE_GAP_KM * sizeUp;
  const tip = new THREE.ConeGeometry(STAKE_RADIUS * sizeUp, tipLength, 20).rotateX(-Math.PI / 2).translate(0, 0, -tipLength / 2);
  // The highest ground within a stake's reach of its spot (a summit on the coarse grid can stand off its cell).
  const groundUnder = (x, y, size = sizeUp) => {
    const reach = STAKE_RADIUS * size * 1.5, dc = W / (columns - 1), dr = H / (rows - 1);
    const c0 = Math.max(0, Math.floor((x - reach) / dc + (columns - 1) / 2)), c1 = Math.min(columns - 1, Math.ceil((x + reach) / dc + (columns - 1) / 2));
    const r0 = Math.max(0, Math.floor((rows - 1) / 2 - (y + reach) / dr)), r1 = Math.min(rows - 1, Math.ceil((rows - 1) / 2 - (y - reach) / dr));
    let top = -Infinity;
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) top = Math.max(top, positions[3 * (r * columns + c) + 2]);
    return top;
  };
  // A label counts as chosen only on a clean tap: a press that wanders more than a few pixels before it lifts (a drag
  // of the map begun on a label, a mouse dragged off and back) chooses nothing. The keyboard's Enter always chooses.
  let pressAt = null;
  const items = data.resorts.map((r, n) => {
    // The body stands on its point, which hangs just over the ground.
    const x = xOf(r.lon), y = yOf(r.lat), z = Math.max(zOf(heightAt(r.lat, r.lon)), groundUnder(x, y)) + gap + tipLength;
    const ghost = new THREE.Mesh(unit, ghostMaterial), fill = new THREE.Mesh(unit, fillMaterial), point = new THREE.Mesh(tip, fillMaterial);
    ghost.position.set(x, y, z); fill.position.set(x, y, z); point.position.set(x, y, z);
    stakes.add(ghost, fill, point);
    const label = document.createElement("button");
    label.className = "map-label";
    label.addEventListener("pointerdown", (e) => { pressAt = {x: e.clientX, y: e.clientY}; });
    label.addEventListener("click", (e) => {
      const from = pressAt; pressAt = null;
      if (from && e.detail && Math.hypot(e.clientX - from.x, e.clientY - from.y) > 8) return;
      if (onSelect) onSelect(r.key);
    });
    overlay.appendChild(label);
    // The snow on the ground now, where the mountain's sensor measures it; null where none does.
    const ground = r.observed && r.observed.depth_in != null ? r.observed.depth_in : null;
    return {key: r.key, name: r.name, backcountry: r.kind === "backcountry", ground, x, y, z, ghost, fill, point, label, n, top: new THREE.Vector3(), width: 80, tall: 40,
      floor: zOf(heightAt(r.lat, r.lon)), off: false};
  });
  // A region with no lake to name has no lake label.
  const lake = region.lake ? document.createElement("div") : null;
  if (lake) { lake.className = "map-lake"; lake.textContent = region.lake.name; overlay.appendChild(lake); }
  const lakeAt = lake && new THREE.Vector3(xOf(region.lake.lon), yOf(region.lake.lat), zOf(heightAt(region.lake.lat, region.lake.lon)) + 0.1);

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

  // ---------- weather radar, laid on the land ----------
  // The national radar mosaic (NEXRAD base reflectivity, from the Iowa Environmental Mesonet's tile cache, redrawn
  // every five minutes). The tiles over the map are drawn onto one canvas and read back once, and each terrain vertex
  // takes the color of the radar pixel over it; where there is no echo it keeps the land's own color. The mountains
  // block the beam from the valley radars, so echoes over the high Sierra are patchy: an absence is not a clear sky.
  // While the radar shows, the land gives up its own colors, its snow and its shading for one flat pale gray, so that
  // the echoes are the only color and the only tone on the map.
  const RADAR_ZOOM = 8, RADAR_TILES = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913", RADAR_TINT = 0.9, RADAR_LAND = [0.9, 0.91, 0.92];
  const radarOf = new Uint8Array(count * 4);
  let radarOn = false;
  async function loadRadar() {
    const n = 2 ** RADAR_ZOOM, tileX = (lon) => (lon + 180) / 360 * n;
    const tileY = (lat) => { const r = lat * Math.PI / 180; return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n; };
    const x0 = Math.floor(tileX(meta.lon_w)), x1 = Math.floor(tileX(meta.lon_e)), y0 = Math.floor(tileY(meta.lat_n)), y1 = Math.floor(tileY(meta.lat_s));
    const sheet = document.createElement("canvas");
    sheet.width = (x1 - x0 + 1) * 256; sheet.height = (y1 - y0 + 1) * 256;
    const pen = sheet.getContext("2d", {willReadFrequently: true}), stamp = Math.floor(Date.now() / 300000);
    const jobs = [];
    for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) jobs.push(new Promise((done) => {
      const tile = new Image();
      tile.crossOrigin = "anonymous";
      tile.onload = () => { pen.drawImage(tile, (x - x0) * 256, (y - y0) * 256); done(true); };
      tile.onerror = () => done(false);
      tile.src = `${RADAR_TILES}/${RADAR_ZOOM}/${x}/${y}.png?t=${stamp}`;
    }));
    const got = await Promise.all(jobs);
    if (!got.some(Boolean)) throw new Error("no radar tiles");
    const pixels = pen.getImageData(0, 0, sheet.width, sheet.height).data;
    for (let v = 0; v < count; v++) {
      const lon = meta.lon_w + (positions[3 * v] / W + 0.5) * (meta.lon_e - meta.lon_w), lat = meta.lat_s + (positions[3 * v + 1] / H + 0.5) * (meta.lat_n - meta.lat_s);
      const px = Math.min(sheet.width - 1, Math.max(0, Math.floor((tileX(lon) - x0) * 256))), py = Math.min(sheet.height - 1, Math.max(0, Math.floor((tileY(lat) - y0) * 256)));
      const at = 4 * (py * sheet.width + px);
      radarOf[4 * v] = pixels[at]; radarOf[4 * v + 1] = pixels[at + 1]; radarOf[4 * v + 2] = pixels[at + 2]; radarOf[4 * v + 3] = pixels[at + 3];
    }
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

  // ---------- the size things are drawn at ----------
  // A region that opens further out than Tahoe's draws its stakes, its road lines and its shields' spacing sizeUp times
  // larger at its opening distance. Closer in they shrink with the distance, down to Tahoe's own size at Tahoe's
  // opening distance, so each view draws them as a map that opened there would. Tahoe's and the Eastern Sierra's
  // (sizeUp 1) never change.
  const scaleAt = (r) => Math.min(sizeUp, Math.max(1, sizeUp * r / openR));
  let drawnAt = sizeUp;
  const standAt = (item, s) => Math.max(item.floor, groundUnder(item.x, item.y, s)) + (STAKE_GAP_KM + STAKE_RADIUS * STAKE_TIP_RADII) * s;
  function scaleTo(s) {
    drawnAt = s;
    const k = s / sizeUp;
    for (const item of items) {
      item.z = standAt(item, s);
      item.fill.scale.x = item.fill.scale.y = item.ghost.scale.x = item.ghost.scale.y = k;
      item.point.scale.setScalar(k);
      item.fill.position.z = item.point.position.z = item.z;
      item.ghost.position.z = item.z + item.fill.scale.z;
    }
    roadWiden.value = s - sizeUp;
    const near = shieldSpreads.reduce((a, b) => Math.abs(Math.log(b / s)) < Math.abs(Math.log(a / s)) ? b : a), set = shieldSets[shieldSpreads.indexOf(near)];
    if (set !== shields) { for (const shield of shields) shield.tag.style.display = "none"; shields = set; }
  }

  // ---------- one part of the region at a time ----------
  // A part ({mountains, look?, zoom?, turnDeg?}) shows only its own mountains (the rest have no stake, no label and no
  // tap target) and frames them; null shows them all from the opening view. The land, roads, shields, water and every
  // layer over the land stay as they are.
  let part = null, framePending = false;
  const fitCamera = new THREE.PerspectiveCamera(), seen = new THREE.Vector3();
  // The nearest view, from this tilt and turn, that holds every stake of the part with its label inside the room the
  // page leaves (framePad: the pixels kept clear at each side, and the boxes of the buttons over the map), centered in that room. It comes no closer than
  // Tahoe's opening distance and goes no further than the region's own limit.
  function fitPart(list, polar, turn) {
    const w = container.clientWidth, h = container.clientHeight, pad = framePad();
    const room = {x0: pad.left, x1: w - pad.right, y0: pad.top, y1: h - pad.bottom};
    fitCamera.copy(camera); fitCamera.up.set(0, 0, 1);
    const tan = Math.tan(fitCamera.fov * Math.PI / 360), right = [Math.cos(turn), Math.sin(turn)], ahead = [-Math.sin(turn), Math.cos(turn)];
    const extent = (r, tx, ty) => {
      fitCamera.position.set(tx + r * Math.sin(polar) * Math.sin(turn), ty - r * Math.sin(polar) * Math.cos(turn), TARGET_Z + r * Math.cos(polar));
      fitCamera.lookAt(tx, ty, TARGET_Z); fitCamera.updateMatrixWorld();
      const s = scaleAt(r), box = {x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity, tags: []};
      for (const item of list) {
        const z = standAt(item, s);
        seen.set(item.x, item.y, z - STAKE_RADIUS * STAKE_TIP_RADII * s).project(fitCamera);
        const bx = (seen.x + 1) / 2 * w, by = (1 - seen.y) / 2 * h;
        seen.set(item.x, item.y, z + Math.max(item.fill.scale.z, 0.02) + 0.7).project(fitCamera);
        const lx = (seen.x + 1) / 2 * w, ly = (1 - seen.y) / 2 * h;
        const tag = {x0: Math.min(bx, lx - item.width / 2 - 2), x1: Math.max(bx, lx + item.width / 2 + 2), y0: ly - item.tall - 12, y1: Math.max(by, ly), item, lx, ly, bx, by, depth: seen.z};
        box.tags.push(tag);
        box.x0 = Math.min(box.x0, tag.x0); box.x1 = Math.max(box.x1, tag.x1); box.y0 = Math.min(box.y0, tag.y0); box.y1 = Math.max(box.y1, tag.y1);
      }
      return box;
    };
    const cx = list.reduce((sum, item) => sum + item.x, 0) / list.length, cy = list.reduce((sum, item) => sum + item.y, 0) / list.length;
    const reach = RADIUS * 0.75;
    // The view at distance r with the stakes and labels centered across the room, and down it either centered or
    // (high=true) against its top, which leaves the buttons low on the sides clear for a closer view.
    const settleAt = (r, high) => {
      let tx = cx, ty = cy, box;
      const per = 2 * r * tan / h;
      for (let n = 0; n < 5; n++) {
        box = extent(r, tx, ty);
        const down = high ? box.y0 - room.y0 : (box.y0 + box.y1 - room.y0 - room.y1) / 2;
        const across = (box.x0 + box.x1 - room.x0 - room.x1) / 2 * per, along = down * per / Math.max(0.3, Math.cos(polar));
        tx += right[0] * across - ahead[0] * along; ty += right[1] * across - ahead[1] * along;
        const d = Math.hypot(tx - lakeX, ty - lakeY);
        if (d > reach) { tx = lakeX + (tx - lakeX) * reach / d; ty = lakeY + (ty - lakeY) * reach / d; }
      }
      box = extent(r, tx, ty);
      // Inside the room, and clear of the buttons over the map (pad.avoid: their boxes).
      const clear = box.tags.every((tag) => !(pad.avoid || []).some((b) => tag.x0 < b.x1 && tag.x1 > b.x0 && tag.y0 < b.y1 && tag.y1 > b.y0));
      // How many labels show, placed as placeLabels places them (the selected first, then the nearest; one that
      // would cover another shrinks to its number, and one that still would is left out).
      // A name in full counts one; one shrunk to its number counts a half. The names are laid out as placeLabels lays
      // them out, and every name that shows and every stake must be inside the room.
      const names = layoutLabels([...box.tags].sort((a, b) => (b.item.key === picked) - (a.item.key === picked) || a.item.backcountry - b.item.backcountry || a.depth - b.depth)
        .map((tag) => ({item: tag.item, x: tag.lx, y: tag.ly})), w);
      const shown = names.reduce((sum, name) => sum + (name.spot[1] ? 0.5 : 1), 0);
      const inside = (b) => b.x0 >= room.x0 && b.x1 <= room.x1 && b.y0 >= room.y0 && b.y1 <= room.y1;
      return {tx, ty, shown, fits: clear && names.every((name) => inside(name.box)) && box.tags.every((tag) => inside({x0: tag.bx, x1: tag.bx, y0: tag.by, y1: tag.by}))};
    };
    // Up a ladder of distances from Tahoe's opening distance: the nearest view that fits and shows the most labels
    // (all of them where any view does).
    const lo = openR / sizeUp, hi = controls.maxDistance, STEPS = 48;
    let best = null, r = hi;
    for (let n = 0; n <= STEPS && !(best && best.shown === list.length); n++) {
      const at = lo * (hi / lo) ** (n / STEPS);
      for (const high of [false, true]) {
        const tried = settleAt(at, high);
        if (tried.fits && (!best || tried.shown > best.shown)) { best = tried; r = at; }
      }
    }
    // Two mountains a few km apart can need a closer view than Tahoe's for both names to show: then the view comes in
    // no further than it takes (down the ladder from Tahoe's distance to CLOSEST_KM), as long as the part still fits.
    // A part whose names cannot all show at any such view keeps the view that shows the most.
    if (best && best.shown < list.length) {
      for (let n = 1; n <= STEPS / 2 && best.shown < list.length; n++) {
        const at = lo * (CLOSEST_KM / lo) ** (n / (STEPS / 2));
        for (const high of [false, true]) {
          const tried = settleAt(at, high);
          if (tried.fits && tried.shown > best.shown) { best = tried; r = at; }
        }
      }
    }
    if (!best) best = settleAt(hi, false);
    return {target: new THREE.Vector3(best.tx, best.ty, TARGET_Z), r, polar, turn, shown: best.shown};
  }
  // Where the camera goes for the part on screen, in the flat view or the tilted one.
  function partView() {
    const polar = flat ? FLAT_POLAR : HOME_POLAR;
    if (!part) return flat ? {target: openTarget.clone(), r: openR, polar, turn: 0} : {target: openTarget.clone(), r: openR, polar, turn: HOME_TURN, position: openPosition.clone()};
    const turn = flat ? 0 : (part.turnDeg ?? region.turnDeg ?? 0) * Math.PI / 180;
    if (part.look && part.zoom) {
      const z = part.zoom, target = new THREE.Vector3(xOf(part.look[1]), yOf(part.look[0]) - 4, TARGET_Z);
      return {target, r: Math.hypot(6 * z, 100 * z, 77 * z), polar, turn};
    }
    // Two mountains close together can stand one behind the other from the region's own direction, so that one's
    // label always covers the other's. Unless the part sets its own turn, the view swings round in steps, nearest
    // first, to the first direction from which every label shows, or failing that the one that shows the most (the
    // flat view stays north up).
    const list = items.filter((item) => !item.off), own = fitPart(list, polar, turn);
    if (own.shown === list.length || flat || part.turnDeg != null) return own;
    let best = own;
    for (const step of [20, -20, 40, -40, 60, -60, 90, -90, 120, -120, 150, -150, 180]) {
      const tried = fitPart(list, polar, turn + step * Math.PI / 180);
      // Another direction wins if it shows more names, or as many from much closer in.
      if (tried.shown > best.shown || (tried.shown === best.shown && tried.r < best.r * 0.75)) best = tried;
      if (best.shown === list.length) break;
    }
    return best;
  }
  function showPart(next, instant = false) {
    part = next && next.mountains ? next : null;
    const keep = part && new Set(part.mountains);
    for (const item of items) {
      item.off = !!keep && !keep.has(item.key);
      item.fill.visible = item.point.visible = !item.off;
      if (item.off) item.ghost.visible = false;
    }
    paintedAt = -1;
    if (instant || !visible || !container.clientWidth || !container.clientHeight) { framePending = true; return; }
    resize();
    flyTo(partView());
  }
  // Puts the camera where the part asks, at once (the map was not on screen when it was chosen).
  function framePart() {
    framePending = false;
    resize();
    const goal = partView();
    glide = null;
    controls.target.copy(goal.target);
    setPose(goal);
    if (goal.position) camera.position.copy(goal.position);
    settle();
  }

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
      const echo = radarOn ? radarOf[4 * v + 3] / 255 * RADAR_TINT : 0;
      for (let k = 0; k < 3; k++) {
        const land = radarOn ? RADAR_LAND[k] : base[3 * v + k] + s * (SNOW[k] - base[3 * v + k]);
        const shown = tint ? land + DANGER_TINT * (tint[k] - land) : land;
        colors[4 * v + k] = echo ? shown + echo * (radarOf[4 * v + k] / 255 - shown) : shown;
      }
    }
    terrain.attributes.color.needsUpdate = true;
    for (const item of items) {
      const all = cumulative[item.n][steps - 1], value = interp(cumulative[item.n], time);
      item.fill.scale.z = Math.max(0.02, value * STAKE_KM_PER_IN);
      // The snow still to come stands on top of the snow so far; two stakes sharing one surface flicker.
      item.ghost.visible = !item.off && all - value > 0.05;
      item.ghost.position.z = item.z + item.fill.scale.z;
      item.ghost.scale.z = Math.max(0.02, (all - value) * STAKE_KM_PER_IN);
      item.fill.material = item.point.material = item.key === picked ? pickMaterial : fillMaterial;
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

  // The side each shown name sat on last frame (see layoutLabels).
  const spotOf = new Map();
  function placeLabels() {
    const w = container.clientWidth, h = container.clientHeight;
    const project = (point) => {
      const p = point.clone().project(camera);
      return {x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, depth: p.z, shown: p.z < 1 && Math.abs(p.x) < 1.02 && Math.abs(p.y) < 1.02};
    };
    // The selected and nearest labels are placed first; one that would cover another moves to one side of its stake,
    // or shrinks to its number (see layoutLabels).
    const placed = [];
    const hits = (r) => placed.some((q) => r.x0 < q.x1 && r.x1 > q.x0 && r.y0 < q.y1 && r.y1 > q.y0);
    // A mountain outside the part of the region on screen has no label, no tap target, and no room kept for it.
    for (const item of items) if (item.off) item.label.style.display = "none";
    const order = items.filter((item) => !item.off).map((item) => {
      item.top.set(item.x, item.y, item.z + Math.max(item.fill.scale.z, 0.02) + 0.7);
      return {item, p: project(item.top)};
    }).sort((a, b) => (b.item.key === picked) - (a.item.key === picked) || a.item.backcountry - b.item.backcountry || a.p.depth - b.p.depth);
    const onScreen = order.filter(({p}) => p.shown);
    for (const {item, p} of order) if (!p.shown) item.label.style.display = "none";
    // A label that finds no room is hidden rather than floated away from its stake.
    const names = layoutLabels(onScreen.map(({item, p}) => ({item, x: p.x, y: p.y, depth: p.depth})), w, spotOf);
    const named = new Map(names.map((name) => [name.item.key, name]));
    spotOf.clear();
    for (const {item, p} of onScreen) {
      const label = item.label, name = named.get(item.key);
      if (!name) { label.style.display = "none"; continue; }
      label.style.display = "";
      placed.push(name.box);
      spotOf.set(item.key, name.spot);
      const [side, mini] = name.spot;
      label.classList.toggle("mini", mini);
      label.classList.toggle("east", side === "e");
      label.classList.toggle("west", side === "w");
      const across = side === "c" ? "-50%" : side === "e" ? `-${Math.min(TAIL_IN, (mini ? 46 : item.width) / 2)}px` : `calc(-100% + ${Math.min(TAIL_IN, (mini ? 46 : item.width) / 2)}px)`;
      label.style.transform = `translate3d(${p.x.toFixed(2)}px, ${(p.y - 6).toFixed(2)}px, 0) translate(${across}, -100%)`;
      label.style.zIndex = String(100000 + Math.round((1 - p.depth) * 100000));
    }
    // Each tag is its own compositor layer (see the page's will-change rule), so it is drawn once and then
    // slid at fractional positions: the motion is smooth and text stays locked to its shape.
    const put = (element, point, allowed = true) => {
      const p = project(point);
      element.style.display = p.shown && allowed ? "" : "none";
      element.style.transform = `translate3d(${p.x.toFixed(2)}px, ${p.y.toFixed(2)}px, 0) translate(-50%, -50%)`;
    };
    if (lake) put(lake, lakeAt);
    // A shield gives way to anything more important: a resort label, or a stake standing in front of it.
    const stakeLines = items.filter((item) => !item.off).map((item) => [project(new THREE.Vector3(item.x, item.y, item.z)), project(item.top)]);
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
    if (framePending && container.clientWidth && container.clientHeight) framePart();
    stepGlide(t);
    sway(t, dt);
    controls.update();
    if (sizeUp > 1) { const s = scaleAt(camera.position.distanceTo(controls.target)); if (Math.abs(s - drawnAt) > drawnAt * 0.01) scaleTo(s); }
    renderer.render(scene, camera);
    placeLabels();
    // The needle's red end points north whichever way the map is turned.
    const ahead = controls.target.clone().sub(camera.position);
    needle.style.transform = `rotate(${(Math.atan2(-ahead.x, ahead.y) * 180 / Math.PI).toFixed(1)}deg)`;
  }
  requestAnimationFrame(frame);
  if (area) showPart(area, true);

  return {
    steps, nowStep, stormActive: storm.active,
    // False when the region's road file is missing or empty: there are no road lines and no shields to show.
    hasRoads: roads.length > 0,
    timeAt: (i) => new Date(hoursUtc[storm.start + Math.min(steps - 1, Math.max(0, Math.round(i)))]),
    rateAt: (i) => interp(rate, i, storm.start),
    quietRate: QUIET_RATE,
    snowLevelFtAt: (i) => interp(snowLevel, i, storm.start) / 0.3048,
    setTime(value) { time = Math.max(0, Math.min(steps - 1, value)); },
    setElevation(value) { level = value; cumulative = series(); paintedAt = -1; },
    // A better figure for the snow on the ground at some mountains (key: inches), in place of the sensor's.
    setGround(byKey) { for (const item of items) if (byKey[item.key] != null) item.ground = byKey[item.key]; paintedAt = -1; },
    // The resorts' reported depths ([feet, inches], 0 for bare ground) as the snow on the ground, only where no sensor
    // reads one; where any does, the sensors' reckoning stands and this does nothing.
    setReportedGround(points) { if (sensed.size) return; packFrom(points, true); paintedAt = -1; },
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
    // Turns the radar on (fetching the latest picture first; rejects if none could be had) or off.
    async showRadar(on) { if (on) await loadRadar(); radarOn = on; ground.material = on ? flatMaterial : litMaterial; paintedAt = -1; },
    // How far the camera is from the point it looks at, in km (for checks).
    cameraDistance: () => camera.position.distanceTo(controls.target),
    northUp() { glideTo({turn: 0}); },
    // Flat is the view from straight above, north up; leaving it tilts back to the opening angle.
    // In a part of the region the view also frames the part again, from above or tilted.
    setFlat(on) { flat = on; if (part) { if (visible) flyTo(partView()); else framePending = true; return; } glideTo(on ? {polar: FLAT_POLAR, turn: 0} : {polar: HOME_POLAR}); },
    // Shows one part of the region ({mountains: [keys], look?, zoom?, turnDeg?}), or all of it (null), moving the view there.
    setArea(next) { showPart(next); },
    dispose() {
      running = false;
      for (const watcher of watchers) watcher.disconnect();
      controls.dispose(); renderer.dispose();
      canvas.remove(); overlay.remove(); compass.remove();
    },
  };
}
