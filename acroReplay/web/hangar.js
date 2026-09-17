// Rendered hangar shown while there's no live data: the aircraft sits on its wheels inside, nose toward the
// open door (north, -z). Everything is procedural — canvas textures and box/plane primitives — so it costs
// nothing to bundle. Dimensions in metres; the aircraft parks at the origin, a little aft of centre.
import * as THREE from 'three';

export const HANGAR = { width: 32, depth: 30, eave: 7.5, ridge: 10.5, door: { width: 22, height: 6.5 } };
const LIT_INTENSITY = 90;

function canvasTexture(w, h, paint, repeat) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  paint(c.getContext('2d'), w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  if (repeat) tex.repeat.set(...repeat);
  return tex;
}

function concrete(repeat) {
  return canvasTexture(512, 512, (g, w, h) => {
    g.fillStyle = '#a4a49f'; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 9000; i += 1) {
      const v = 140 + Math.random() * 60;
      g.fillStyle = `rgba(${v},${v},${v - 4},${0.25 + Math.random() * 0.4})`;
      g.fillRect(Math.random() * w, Math.random() * h, 2, 2);
    }
    for (let i = 0; i < 30; i += 1) {
      const x = Math.random() * w, y = Math.random() * h, r = 20 + Math.random() * 70;
      const grad = g.createRadialGradient(x, y, 0, x, y, r);
      grad.addColorStop(0, 'rgba(50,50,50,0.12)'); grad.addColorStop(1, 'rgba(50,50,50,0)');
      g.fillStyle = grad; g.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
    g.strokeStyle = 'rgba(40,40,40,0.5)'; g.lineWidth = 6;   // expansion joints at the tile edges
    g.strokeRect(0, 0, w, h);
  }, repeat);
}

function corrugated(repeat) {
  return canvasTexture(256, 64, (g, w, h) => {
    for (let x = 0; x < w; x += 16) {
      const grad = g.createLinearGradient(x, 0, x + 16, 0);
      grad.addColorStop(0, '#b6bdc4'); grad.addColorStop(0.5, '#e3e7eb'); grad.addColorStop(1, '#a5acb3');
      g.fillStyle = grad; g.fillRect(x, 0, 16, h);
    }
  }, repeat);
}

function banner() {
  return canvasTexture(1024, 256, (g, w, h) => {
    g.fillStyle = '#1b2530'; g.fillRect(0, 0, w, h);
    g.fillStyle = '#0a84ff'; g.fillRect(0, h - 14, w, 14);
    g.fillStyle = '#f4f6f8';
    g.font = 'bold 150px -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif';
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('WingRock', w / 2, h / 2 - 6);
  });
}

/// Adds the hangar to `scene` and returns its group. The interior point lights live directly in the scene
/// (so toggling the hangar doesn't change the light count and recompile every shader); `group.userData.setLit`
/// turns them on and off with the hangar.
export function buildHangar(scene) {
  const g = new THREE.Group();
  const { width: W, depth: D, eave: E, ridge: R, door } = HANGAR;
  const z0 = -D / 2 + 2, z1 = z0 + D, zc = (z0 + z1) / 2;   // door plane z0 (north), back wall z1
  const wallMat = (len) => new THREE.MeshStandardMaterial({ map: corrugated([len, 1]), roughness: 0.6, metalness: 0.35, side: THREE.DoubleSide });
  const gableMat = new THREE.MeshStandardMaterial({ color: 0xc9d0d6, roughness: 0.6, metalness: 0.35, side: THREE.DoubleSide });
  const roofMat = new THREE.MeshStandardMaterial({ color: 0x6d7580, roughness: 0.7, metalness: 0.4, side: THREE.DoubleSide });
  const steel = new THREE.MeshStandardMaterial({ color: 0x3b4149, roughness: 0.6, metalness: 0.5 });
  const plane = (w, h, mat) => new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat);
  const box = (w, h, d, mat) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  const put = (m, x, y, z, rx = 0, ry = 0, rz = 0) => { m.position.set(x, y, z); m.rotation.set(rx, ry, rz); g.add(m); return m; };

  // Floor, and the apron outside the door.
  put(plane(W, D, new THREE.MeshStandardMaterial({ map: concrete([W / 4, D / 4]), roughness: 0.9 })), 0, 0.01, zc, -Math.PI / 2);
  put(plane(W + 14, 26, new THREE.MeshStandardMaterial({ color: 0x4a4b4d, roughness: 1 })), 0, 0.005, z0 - 13, -Math.PI / 2);

  // Side walls, back wall, gables, and the front wall around the door opening.
  put(plane(D, E, wallMat(D)), -W / 2, E / 2, zc, 0, Math.PI / 2);
  put(plane(D, E, wallMat(D)), W / 2, E / 2, zc, 0, -Math.PI / 2);
  put(plane(W, E, wallMat(W)), 0, E / 2, z1);
  const gable = new THREE.ShapeGeometry(new THREE.Shape([new THREE.Vector2(-W / 2, E), new THREE.Vector2(W / 2, E), new THREE.Vector2(0, R)]));
  put(new THREE.Mesh(gable, gableMat), 0, 0, z1);
  put(new THREE.Mesh(gable, gableMat), 0, 0, z0);
  const jamb = (W - door.width) / 2;
  put(plane(jamb, E, wallMat(jamb)), -(W - jamb) / 2, E / 2, z0);
  put(plane(jamb, E, wallMat(jamb)), (W - jamb) / 2, E / 2, z0);
  put(plane(door.width, E - door.height, wallMat(door.width)), 0, (E + door.height) / 2, z0);

  // Gable roof: two slabs hinged at the ridge (lie flat first, then tilt — hence the ZYX order).
  const half = Math.hypot(W / 2, R - E), slope = Math.atan2(R - E, W / 2);
  for (const sx of [-1, 1]) {
    const slab = put(plane(half, D, roofMat), sx * W / 4, (E + R) / 2, zc);
    slab.rotation.set(-Math.PI / 2, 0, -sx * slope, 'ZYX');
  }

  // Steel: columns, and a truss under the roof at each column line.
  const rafterLen = Math.hypot(W / 2, R - E);
  const bays = Math.round(D / 6);
  for (let i = 0; i <= bays; i += 1) {
    const z = z0 + 0.6 + (i * (D - 1.2)) / bays;
    for (const sx of [-1, 1]) put(box(0.18, E, 0.18, steel), sx * (W / 2 - 0.1), E / 2, z);
    put(box(W, 0.14, 0.14, steel), 0, E - 0.07, z);
    for (const sx of [-1, 1]) {
      put(box(rafterLen, 0.12, 0.12, steel), sx * W / 4, (E + R) / 2 - 0.1, z, 0, 0, -sx * slope);
      put(box(0.08, Math.hypot(W / 4, R - E), 0.08, steel), sx * W / 8, (E + R) / 2, z, 0, 0, sx * Math.atan2(W / 4, R - E));
    }
    put(box(0.1, R - E, 0.1, steel), 0, (E + R) / 2, z);
  }

  // Light fixtures under the trusses; the actual lights are point lights in the scene.
  const bulb = new THREE.MeshBasicMaterial({ color: 0xfff4dc });
  for (const x of [-W / 4, W / 4]) {
    for (let z = z0 + 4; z < z1 - 2; z += 6) {
      put(box(1.6, 0.1, 0.4, bulb), x, E - 0.6, z);
      put(box(0.05, 0.5, 0.05, steel), x, E - 0.3, z);
    }
  }
  const lights = [[-W / 5, zc - 4], [W / 5, zc + 3]].map(([x, z]) => {
    const l = new THREE.PointLight(0xfff1dc, 0, 0, 2);
    l.position.set(x, E - 1, z);
    scene.add(l);
    return l;
  });

  // Dressing: workbench and tool chest along the back wall, drums in the corners, chocks at the main wheels.
  const wood = new THREE.MeshStandardMaterial({ color: 0x8b6a3e, roughness: 0.8 });
  const red = new THREE.MeshStandardMaterial({ color: 0xc1272d, roughness: 0.5, metalness: 0.3 });
  const blue = new THREE.MeshStandardMaterial({ color: 0x1f4e8c, roughness: 0.5, metalness: 0.3 });
  const yellow = new THREE.MeshStandardMaterial({ color: 0xe8b400, roughness: 0.6 });
  const bx = W / 4;
  put(box(3, 0.08, 0.9, wood), bx, 0.9, z1 - 0.55);
  for (const dx of [-1.4, 1.4]) put(box(0.08, 0.86, 0.8, steel), bx + dx, 0.43, z1 - 0.55);
  put(box(0.9, 1.0, 0.5, red), -bx, 0.55, z1 - 0.4);
  const drum = new THREE.CylinderGeometry(0.29, 0.29, 0.88, 20);
  put(new THREE.Mesh(drum, blue), W / 2 - 1.4, 0.44, z1 - 1.0);
  put(new THREE.Mesh(drum, blue), W / 2 - 2.0, 0.44, z1 - 0.5);
  put(new THREE.Mesh(drum, yellow), -(W / 2 - 1.3), 0.44, z1 - 2.2);
  for (const x of [-0.87, 0.87]) put(box(0.3, 0.12, 0.14, yellow), x, 0.06, -1.15);
  put(plane(10, 2.5, new THREE.MeshBasicMaterial({ map: banner() })), 0, E - 2, z1 - 0.03, 0, Math.PI);

  g.userData.setLit = (on) => { for (const l of lights) l.intensity = on ? LIT_INTENSITY : 0; };
  g.visible = false;
  scene.add(g);
  return g;
}
