// Aerial-imagery ground: Web Mercator tiles laid out in the local frame (x east, z south) around the origin.
// Tries a bundled copy first (web/tiles/{z}/{x}/{y}.jpg, for the no-internet cockpit), then Esri World Imagery
// (global coverage incl. ocean), then the USGS National Map imagery service (public domain, land only).
import * as THREE from 'three';

const EARTH_RADIUS_M = 6378137;
const DEG = Math.PI / 180;
export const REMOTE_TILE_URL = 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}';
export const LOCAL_TILE_URL = './tiles/{z}/{x}/{y}.jpg';
export const ESRI_TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
export const ATTRIBUTION = 'Imagery: Esri World Imagery · USGS The National Map';

function tileIndex(lat, lon, z) {
  const n = 2 ** z;
  const latR = lat * DEG;
  return {
    x: Math.floor(((lon + 180) / 360) * n),
    y: Math.floor(((1 - Math.log(Math.tan(latR) + 1 / Math.cos(latR)) / Math.PI) / 2) * n),
  };
}

function tileBounds(x, y, z) {
  const n = 2 ** z;
  const lat = (yy) => Math.atan(Math.sinh(Math.PI * (1 - (2 * yy) / n))) / DEG;
  return { west: (x / n) * 360 - 180, east: ((x + 1) / n) * 360 - 180, north: lat(y), south: lat(y + 1) };
}

function fill(template, z, x, y) {
  return template.replace('{z}', z).replace('{x}', x).replace('{y}', y);
}

const LEVELS = [{ z: 16, radiusM: 1500 }, { z: 14, radiusM: 9000 }, { z: 12, radiusM: 45000 }, { z: 10, radiusM: 160000 }];

// A bundled tile set announces itself with tiles/index.json; without it we go straight to the remote server.
async function hasLocalTiles() {
  try { return (await fetch('./tiles/index.json', { cache: 'no-store' })).ok; } catch (e) { return false; }
}

export async function buildTileGround(scene, [lat0, lon0], levels = LEVELS) {
  const group = new THREE.Group();
  scene.add(group);
  const local = await hasLocalTiles();
  const loader = new THREE.TextureLoader();
  loader.setCrossOrigin('anonymous');
  const mPerDegLat = EARTH_RADIUS_M * DEG;
  const mPerDegLon = mPerDegLat * Math.cos(lat0 * DEG);
  const toLocal = (lat, lon) => ({ east: (lon - lon0) * mPerDegLon, north: (lat - lat0) * mPerDegLat });
  const finerRadius = [];
  let count = 0;
  levels.forEach((lvl, i) => {
    const dLat = lvl.radiusM / mPerDegLat, dLon = lvl.radiusM / mPerDegLon;
    const a = tileIndex(lat0 + dLat, lon0 - dLon, lvl.z), b = tileIndex(lat0 - dLat, lon0 + dLon, lvl.z);
    for (let x = a.x; x <= b.x; x += 1) {
      for (let y = a.y; y <= b.y; y += 1) {
        const bb = tileBounds(x, y, lvl.z);
        const sw = toLocal(bb.south, bb.west), ne = toLocal(bb.north, bb.east);
        const cx = (sw.east + ne.east) / 2, cn = (sw.north + ne.north) / 2;
        if (finerRadius.some((r) => Math.abs(cx) < r && Math.abs(cn) < r)) continue;
        // Ground layers don't write depth and draw coarse → fine, so imagery never z-fights the base plane.
        const mat = new THREE.MeshBasicMaterial({ color: 0x6f9a5c, depthWrite: false });
        const mesh = new THREE.Mesh(new THREE.PlaneGeometry(ne.east - sw.east, ne.north - sw.north), mat);
        mesh.rotation.x = -Math.PI / 2;
        mesh.position.set(cx, 0, -cn);
        mesh.renderOrder = -10 + (levels.length - i);
        group.add(mesh);
        count += 1;
        const apply = (tex) => {
          tex.colorSpace = THREE.SRGBColorSpace;
          tex.anisotropy = 8;
          mat.map = tex;
          mat.color.set(0xffffff);
          mat.needsUpdate = true;
        };
        const usgs = () => loader.load(fill(REMOTE_TILE_URL, lvl.z, x, y), apply, undefined, () => {});
        const remote = () => loader.load(fill(ESRI_TILE_URL, lvl.z, x, y), apply, undefined, usgs);
        if (local) loader.load(fill(LOCAL_TILE_URL, lvl.z, x, y), apply, undefined, remote); else remote();
      }
    }
    finerRadius.push(lvl.radiusM);
  });
  console.info(`tile ground: ${count} tiles around ${lat0.toFixed(4)}, ${lon0.toFixed(4)}`);
  return group;
}
