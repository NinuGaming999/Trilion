import * as THREE from 'three';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Rig, B } from './rig.js';
import { Face } from './face.js';
import { Animator } from './anim.js';
import { Mind, CANNED } from './mind.js';

const CFG = window.TRILION_CONFIG || {}, TOKEN = window.TRILION_TOKEN || '';
const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const canvas = $('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0x000000, 0);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(28, 1, 0.05, 50);
const controls = new OrbitControls(camera, canvas);
Object.assign(controls, { enableDamping: true, enablePan: false, minDistance: 1.2, maxDistance: 6, minPolarAngle: 0.95, maxPolarAngle: 1.8, minAzimuthAngle: -1.1, maxAzimuthAngle: 1.1 });
const VIEWS = { bust: [[0, 1.42, 3.3], [0, 1.27, 0]], full: [[0, 1.1, 5.4], [0, 0.95, 0]], face: [[0, 1.58, 1.5], [0, 1.52, 0]] };
function setView(n) { const [p, t] = VIEWS[n]; camera.position.set(...p); controls.target.set(...t); controls.update(); }
setView('bust');

scene.add(new THREE.HemisphereLight(0xcfe3ff, 0x25182c, 1.1));
const key = new THREE.DirectionalLight(0xffffff, 1.5); key.position.set(1.6, 2.6, 3.2); scene.add(key);
const rim = new THREE.DirectionalLight(0xff3b4e, 1.0); rim.position.set(-2, 2, -2.5); scene.add(rim);
const rim2 = new THREE.DirectionalLight(0x4aa8ff, 0.6); rim2.position.set(2.4, 1.6, -2); scene.add(rim2);

const A = { ready: false, THREE, scene, camera, renderer, controls, B, fp: null, setView };
window.__avatar = A;
function resize() { const w = window.innerWidth, h = window.innerHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
window.addEventListener('resize', resize); resize();

// ---------------------------------------------------------------- embers / pyro aura
const N = 240, ePos = new Float32Array(N * 3), eVel = new Float32Array(N), eSeed = new Float32Array(N);
function resetEmber(i, anywhere) { const a = Math.random() * 6.28, r = 0.15 + Math.random() * 0.5; ePos[i * 3] = Math.cos(a) * r; ePos[i * 3 + 1] = anywhere ? Math.random() * 2 : 0.05; ePos[i * 3 + 2] = Math.sin(a) * r * 0.7; eVel[i] = 0.12 + Math.random() * 0.4; eSeed[i] = Math.random() * 6.28; }
for (let i = 0; i < N; i++) resetEmber(i, true);
const eGeo = new THREE.BufferGeometry(); eGeo.setAttribute('position', new THREE.BufferAttribute(ePos, 3));
const sprite = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d'); const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32); gr.addColorStop(0, 'rgba(255,230,180,1)'); gr.addColorStop(0.3, 'rgba(255,90,60,.7)'); gr.addColorStop(1, 'rgba(255,40,40,0)'); g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); })();
const eMat = new THREE.PointsMaterial({ size: 0.05, map: sprite, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.35 });
const embers = new THREE.Points(eGeo, eMat); embers.frustumCulled = false; scene.add(embers);

// ---------------------------------------------------------------- load
async function texturesReady(root, ms = 20000) {
  const maps = [];
  root.traverse((o) => { if (o.isMesh) for (const m of (Array.isArray(o.material) ? o.material : [o.material])) { if (m.map) maps.push(m.map); if (m.normalMap) maps.push(m.normalMap); } });
  const t0 = performance.now();
  while (performance.now() - t0 < ms) {
    if (maps.every((t) => t.image && (t.image.width > 0 || t.image.naturalWidth > 0) && t.image.complete !== false)) return true;
    await new Promise((r) => setTimeout(r, 50));
  }
  return false;
}
const mind = new Mind(), meshes = []; let anim = null;
async function waitModel() {
  for (;;) {
    const s = await (await fetch('/avatar/status', { cache: 'no-store' })).json();
    if (s.model_ready) return;
    if (s.error) throw new Error(s.error);
    $('loadtxt').textContent = s.downloading ? 'Downloading her model (first time only)...' : 'Preparing...';
    await new Promise((r) => setTimeout(r, 800));
  }
}
async function load() {
  await waitModel();
  $('loadtxt').textContent = 'Waking up...';
  const root = await new FBXLoader().loadAsync(CFG.model, (e) => { if (e.total) $('loadfill').style.width = (100 * e.loaded / e.total) + '%'; });
  const box = new THREE.Box3().setFromObject(root), size = box.getSize(new THREE.Vector3());
  const s = 1.75 / size.y;
  root.scale.setScalar(s);
  root.position.set(-(box.min.x + size.x / 2) * s, -box.min.y * s, -(box.min.z + size.z / 2) * s);
  root.traverse((o) => { if (o.isMesh) { o.frustumCulled = false; meshes.push(o); } });
  scene.add(root);
  $('loadtxt').textContent = 'Loading textures...';
  await texturesReady(root);
  A.root = root; A.rig = new Rig(THREE, root); A.face = new Face(THREE, root, A.rig);
  A.fp = { lidL: { closed: 0, tilt: 0, low: 0 }, lidR: { closed: 0, tilt: 0, low: 0 }, mouth: { open: 0, width: 0, smile: 0 }, gaze: { x: 0, y: 0 } };
  anim = new Animator(A); A.anim = anim; A.mind = mind;
  A.ready = true;
  $('load').classList.add('done');
}
load().catch((e) => { $('loadtxt').textContent = 'Could not load her: ' + e; console.error(e); });

const ctx = { state: 'idle', out: 0, mic: 0, localOut: 0, anger: 0, level: 'calm', sulking: false, cam: { yaw: 0 }, pointer: { x: 0, y: 0, age: 99 } };
A.ctx = ctx;
let now = 0;

// ---------------------------------------------------------------- bubble + network
let bubbleTimer = 0;
function bubble(text, cls = '', ms = 2800) { const b = $('bubble'); b.textContent = text; b.className = 'show ' + cls; clearTimeout(bubbleTimer); bubbleTimer = setTimeout(() => { b.className = ''; }, ms); }
async function post(path, body) {
  try { return await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Trilion-Token': TOKEN }, body: JSON.stringify(body) }); } catch (e) { return null; }
}
A.post = post;
let lastLineId = 0, lastReplyId = 0, connected = false, first = true;
const EMO_CLASS = { angry: 'angry', furious: 'angry', annoyed: 'angry' };
function onLine(l) {
  bubble(l.text, EMO_CLASS[l.emotion] || '', 4500 + l.text.length * 70);
  if (l.emotion) anim.setEmotion(l.emotion, 6);
  const g = l.gesture;
  if (g && g !== 'none') anim.play(g, { side: Math.random() < 0.5 ? -1 : 1, dur: g === 'turn_away' ? 2.6 : undefined });
}
let polling = false;
async function poll() {
  if (polling || !anim) return; polling = true;
  try {
    const S = window.__fakeState || await (await fetch('/state', { cache: 'no-store' })).json();   // __fakeState: test hook
    connected = true;
    ctx.state = S.state || 'idle'; ctx.out = clamp(S.out || 0, 0, 1); ctx.mic = clamp(S.mic || 0, 0, 1);
    const av = S.avatar || {};
    if (av.line && av.line.id !== lastLineId) { lastLineId = av.line.id; onLine(av.line); }
    const last = (S.events || []).filter((e) => e.k === 'reply').pop();
    if (last && last.id && last.id !== lastReplyId) {
      lastReplyId = last.id;
      if (!first) {
        bubble(last.text, '', 3000 + last.text.length * 55);
        if (/sorry|error|couldn't|could not|failed|can't/i.test(last.text)) anim.setEmotion('sad', 3);
        else if (/!|haha|great|nice/i.test(last.text)) anim.setEmotion('amused', 3);
        else if (/\?/.test(last.text)) anim.setEmotion('curious', 3);
      }
    }
    if (first) { first = false; if (last && last.id) lastReplyId = last.id; setTimeout(() => post('/avatar/event', { type: 'hello' }), 1500); }
  } catch (e) { connected = false; ctx.state = 'idle'; ctx.out = 0; }
  polling = false;
}
setInterval(poll, 100);
$('bar').addEventListener('submit', (e) => { e.preventDefault(); const i = $('say'), t = i.value.trim(); if (!t) return; i.value = ''; post('/avatar/say', { text: t }); bubble('...', '', 1500); });

// ---------------------------------------------------------------- instant stock lines (pre-synthesised by Trilion's voice)
const slug = (t) => t.toLowerCase().replace(/[^a-z]+/g, '-').replace(/^-+|-+$/g, '') || 'line';
let actx = null, analyser = null, filler = null, aBuf = null;
function playFiller(text) {
  try {
    if (filler) filler.pause();
    const a = new Audio('/avatar/audio/' + slug(text) + '.wav'); a.volume = 0.9; filler = a;
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    const src = actx.createMediaElementSource(a); analyser = actx.createAnalyser(); analyser.fftSize = 256; aBuf = new Uint8Array(analyser.fftSize);
    src.connect(analyser); analyser.connect(actx.destination);
    a.play().catch(() => {});
  } catch (e) { /* no audio: the text bubble still shows */ }
}
function fillerLevel() {
  if (!filler || filler.paused || filler.ended || !analyser) return 0;
  analyser.getByteTimeDomainData(aBuf); let s = 0; for (const v of aBuf) { const d = (v - 128) / 128; s += d * d; } return clamp(Math.sqrt(s / aBuf.length) * 4, 0, 1);
}

// ---------------------------------------------------------------- touching her
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), tmp = new THREE.Vector3();
const ZONE_BONES = [['neck', [B.neck]], ['head', [B.head]], ['chest', [B.chest, B.spine2]], ['belly', [B.spine1, B.hips]],
  ['arm', [B.armL, B.foreL, B.armR, B.foreR, B.clavL, B.clavR]], ['hand', [B.handL, B.handR]],
  ['leg', [B.thighL, B.thighR, 'ValveBipedBip01_L_Calf', 'ValveBipedBip01_R_Calf']]];
function pick(ev) {
  if (!A.ready) return null;
  const r = canvas.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  return ray.intersectObjects(meshes, false)[0] || null;
}
function zoneOf(hit) {
  const m = hit.object.material.name;
  if (m === 'face') return 'face';
  if (m === 'hair') return 'hair';
  let best = 'other', bd = 1e9;
  for (const [z, names] of ZONE_BONES) for (const n of names) {
    const b = A.rig.bones[n] && A.rig.bones[n][0]; if (!b) continue;
    b.getWorldPosition(tmp); const d = tmp.distanceTo(hit.point); if (d < bd) { bd = d; best = z; }
  }
  if ((best === 'chest' || best === 'belly') && hit.face) { const nrm = hit.face.normal.clone().transformDirection(hit.object.matrixWorld); if (nrm.z < -0.35) best = 'back'; }
  return best;
}
let lastInteraction = 0;
function touch(zone, kind, hit) {
  const res = mind.touch(zone, kind, now);
  for (const c of res.clips) {
    if (c.clip === 'pullArm' && hit) c.side = hit.point.x < 0 ? 1 : -1;
    if (c.clip === 'snap') anim.sulkSide = c.side;
    anim.play(c.clip, c);
  }
  bubble(res.canned, res.level === 'calm' ? '' : 'angry', 2200); playFiller(res.canned);
  if (res.snap) for (let i = 0; i < N; i++) { resetEmber(i, false); eVel[i] *= 2.5; }
  if (res.needAI) post('/avatar/event', { type: 'touch', zone, kind, level: res.level, anger: +res.anger.toFixed(2), count: mind.touches.length, sulking: mind.sulking(now), snap: res.snap });
  lastInteraction = now;
}
let down = null, hoverAt = 0;
canvas.addEventListener('pointerdown', (e) => {
  const hit = pick(e);
  if (hit) { controls.enabled = false; down = { x: e.clientX, y: e.clientY, t: now, hit, zone: zoneOf(hit), moved: 0, lastHold: now, lastStroke: now }; canvas.setPointerCapture(e.pointerId); }
});
canvas.addEventListener('pointermove', (e) => {
  const r = canvas.getBoundingClientRect();
  ctx.pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1; ctx.pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1; ctx.pointer.age = 0;
  if (down) {
    down.moved += Math.hypot(e.movementX || 0, e.movementY || 0);
    if (down.moved > 40 && now - down.lastStroke > 0.6) { const h = pick(e); if (h) { down.zone = zoneOf(h); down.hit = h; touch(down.zone, 'stroke', h); down.lastStroke = now; } }
  } else if (performance.now() - hoverAt > 80) { hoverAt = performance.now(); canvas.style.cursor = pick(e) ? 'pointer' : 'grab'; }
});
function release() { if (!down) return; if (down.moved < 12 && now - down.t < 0.55) touch(down.zone, 'poke', down.hit); controls.enabled = true; down = null; }
canvas.addEventListener('pointerup', release); canvas.addEventListener('pointercancel', release);
canvas.addEventListener('dblclick', () => setView('bust'));
window.addEventListener('keydown', (e) => { if (e.target.tagName === 'INPUT') return; const k = e.key.toLowerCase(); if (k === 'f') setView('full'); if (k === 'b') setView('bust'); if (k === 'c') setView('face'); });

// ---------------------------------------------------------------- frame loop
const clock = new THREE.Clock();
let nextBored = 150 + Math.random() * 120;
(function loop() {
  requestAnimationFrame(loop);
  const dt = Math.min(0.05, clock.getDelta()); now = clock.elapsedTime;
  ctx.pointer.age += dt;
  if (A.ready) {
    const m = mind.update(dt, now);
    ctx.anger = mind.anger; ctx.level = mind.level(); ctx.sulking = m.sulking; ctx.localOut = fillerLevel();
    ctx.cam.yaw = Math.atan2(camera.position.x - controls.target.x, camera.position.z - controls.target.z);
    if (m.cooled) { const l = CANNED.cooled[Math.floor(Math.random() * 3)]; bubble(l, '', 2600); playFiller(l); anim.setEmotion('calm', 3); post('/avatar/event', { type: 'cooled' }); }
    if (down && down.moved < 12 && now - down.t > 0.55 && now - down.lastHold > 0.8) { down.lastHold = now; touch(down.zone, 'hold', down.hit); }
    if (connected && ctx.state === 'idle' && now - lastInteraction > nextBored) { lastInteraction = now; nextBored = 150 + Math.random() * 150; post('/avatar/event', { type: 'idle' }); }
    A.rig.reset(); anim.update(dt, ctx); A.face.update(A.fp); A.rig.apply();
    $('stat').textContent = (connected ? ctx.state : 'offline') + ' \u00b7 ' + ctx.level + (ctx.sulking ? ' \u00b7 sulking' : '');
    $('moodfill').style.width = Math.round(mind.anger * 100) + '%';
    const aura = clamp(anim.ch.aura || 0, 0, 1.2);
    $('vig').style.opacity = String(clamp(aura * 0.55, 0, 0.6));
    rim.intensity = 1.0 + 2.6 * aura; eMat.opacity = 0.3 + 0.55 * Math.min(1, aura); eMat.size = 0.045 + 0.05 * Math.min(1, aura);
    for (let i = 0; i < N; i++) {
      ePos[i * 3 + 1] += eVel[i] * (0.4 + aura * 1.4) * dt; ePos[i * 3] += Math.sin(now * 1.3 + eSeed[i]) * 0.05 * dt;
      if (ePos[i * 3 + 1] > 2.1) resetEmber(i, false);
    }
    eGeo.attributes.position.needsUpdate = true;
  }
  controls.update();
  renderer.render(scene, camera);
})();
