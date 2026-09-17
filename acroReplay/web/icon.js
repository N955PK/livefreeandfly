// Dev tool: renders the Eagle straight down (nose up) onto a dark background and POSTs the PNG to the bridge,
// which saves it as sessions/icon.png for the iOS asset catalog. Not part of the app.
import * as THREE from 'three';
import { OBJLoader } from 'three/addons/OBJLoader.js';
import { MTLLoader } from 'three/addons/MTLLoader.js';

const canvas = document.getElementById('out');
const msg = document.getElementById('msg');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(1024, 1024, false);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b1220);
scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.3));
const sun = new THREE.DirectionalLight(0xffffff, 1.8); sun.position.set(-3, 10, 4); scene.add(sun);
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
camera.up.set(0, 0, -1);           // north (nose) up on the icon
// Frame the model's footprint: look straight down at its centre, square view a little wider than its longest extent.
function frame(target) {
  const bb = new THREE.Box3().setFromObject(target);
  const c = bb.getCenter(new THREE.Vector3()), size = bb.getSize(new THREE.Vector3());
  const half = Math.max(size.x, size.z) / 2 * 1.12;
  camera.left = -half; camera.right = half; camera.top = half; camera.bottom = -half;
  camera.position.set(c.x, 20, c.z);
  camera.lookAt(c.x, 0, c.z);
  camera.updateProjectionMatrix();
}

const path = './models/eagle/';
new MTLLoader().setPath(path).load('eagle.mtl', (mtl) => {
  mtl.preload();
  new OBJLoader().setMaterials(mtl).setPath(path).load('eagle.obj', (obj) => {
    obj.traverse((m) => {
      if (!m.isMesh) return;
      if (/canopy/i.test(m.name)) m.material = new THREE.MeshStandardMaterial({ color: 0x9fc5e8, transparent: true, opacity: 0.5, roughness: 0.1 });
      else if (/propeller/i.test(m.name)) m.visible = false;
      else m.material.side = THREE.DoubleSide;
    });
    // model: cm, Y up, nose +Z → world: metres, nose toward -z (north)
    const pivot = new THREE.Group();
    pivot.scale.setScalar(0.01);
    pivot.rotation.y = Math.PI;
    obj.position.set(0, 0, -30);
    pivot.add(obj);
    scene.add(pivot);
    frame(pivot);
    renderer.render(scene, camera);
    canvas.toBlob(async (blob) => {
      const r = await fetch('/dev/icon', { method: 'POST', body: blob });
      msg.textContent = r.ok ? `saved (${blob.size} bytes)` : `save failed: ${r.status}`;
    }, 'image/png');
  }, undefined, (e) => { msg.textContent = 'obj failed ' + e; });
}, undefined, (e) => { msg.textContent = 'mtl failed ' + e; });
