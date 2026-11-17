// Animator: always-on idle life + state behaviours + emotions + one-shot clips (reactions, gestures) + hair/coat physics.
// Nothing here waits for the AI: every channel eases toward its target, so she is never frozen or popping.
import { B } from './rig.js';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const damp = (cur, tgt, hl, dt) => cur + (tgt - cur) * (1 - Math.pow(2, -dt / hl));
const ease = (x) => x * x * (3 - 2 * x);
export const noise = (t, s = 0) => (Math.sin(t + s * 12.9) + 0.6 * Math.sin(t * 2.3 + s * 7.1) + 0.8 * Math.sin(t * 0.37 + s * 3.3)) / 2.4;
const env = (p, a = 0.15, r = 0.6) => ease(p < a ? p / a : p > 1 - r ? (1 - p) / r : 1);

export const ARM_POSES = {
  hang: { armR: [0, 0, 0.5], armL: [0, 0, -0.5], foreR: [-0.2, 0, 0], foreL: [-0.2, 0, 0] },
  front: { armR: [-0.35, 0, 0.45], armL: [-0.35, 0, -0.45], foreR: [-1.15, 0, 0], foreL: [-1.15, 0, 0] },
  front2: { armR: [-0.5, 0.25, 0.35], armL: [-0.5, -0.25, -0.35], foreR: [-1.3, 0.3, 0], foreL: [-1.3, -0.3, 0] },
  speakL: { armR: [0, 0, 0.5], armL: [-0.55, 0, -0.3], foreR: [-0.2, 0, 0], foreL: [-1.45, 0, 0] },
  speakR: { armR: [-0.55, 0, 0.3], armL: [0, 0, -0.5], foreR: [-1.45, 0, 0], foreL: [-0.2, 0, 0] },
  explain: { armR: [-1.0, 0.2, 0.1], armL: [0, 0, -0.5], foreR: [-1.9, 0, 0], foreL: [-0.2, 0, 0] },
  threat: { armR: [-0.55, 0.55, 0.3], armL: [-0.55, -0.55, -0.3], foreR: [-1.5, 0.7, 0], foreL: [-1.5, -0.7, 0] },
};
const ARM_KEYS = ['armR', 'armL', 'foreR', 'foreL'];
export const EMOTIONS = {
  neutral: { lid: 0, tilt: 0, low: 0, smile: 0, headP: 0, lean: 0 },
  curious: { lid: 0, tilt: -0.1, low: 0, smile: 0, headP: -0.02, lean: 0.02, headR: 0.1 },
  amused: { lid: 0.1, tilt: -0.15, low: 0.4, smile: 0.7, headP: 0.0, lean: 0, headR: -0.05 },
  annoyed: { lid: 0.22, tilt: 0.55, low: 0, smile: 0, headP: 0.05, lean: 0.02 },
  angry: { lid: 0.38, tilt: 1.0, low: 0, smile: 0, headP: 0.11, lean: 0.06 },
  furious: { lid: 0.5, tilt: 1.3, low: 0, smile: 0, headP: 0.16, lean: 0.1 },
  sad: { lid: 0.3, tilt: -0.8, low: 0, smile: 0, headP: 0.1, lean: 0 },
  calm: { lid: 0.04, tilt: 0, low: 0, smile: 0.1, headP: 0, lean: 0 },
};
export const GESTURES = ['none', 'nod', 'shake_head', 'glare', 'turn_away', 'sigh', 'point', 'tilt', 'shrug'];

export class Animator {
  constructor(A) {
    this.A = A; this.t = 0;
    this.ch = {}; this.clips = []; this.arm = {}; this.armHold = 0; this.armTo = 'hang';
    for (const k of ARM_KEYS) this.arm[k] = [...ARM_POSES.hang[k]];
    this.gaze = { tx: 0, ty: 0, next: 0 };
    this.blink = { t: -1, next: 2.5, dbl: false };
    this.idleNext = 7; this.weight = 0; this.weightT = 0; this.speakGestureNext = 2; this.lastOut = 0; this.nodCool = 0;
    this.emotion = 'neutral'; this.emotionUntil = 0; this.sulkSide = 1; this.jig = new Jiggle(A.rig);
  }
  setEmotion(name, secs = 4) { if (EMOTIONS[name]) { this.emotion = name; this.emotionUntil = this.t + secs; } }
  poseArms(name, secs = 2.5) { if (ARM_POSES[name]) { this.armTo = name; this.armHold = this.t + secs; } }
  play(name, o = {}) {
    const dur = o.dur || { flinch: 0.9, recoil: 1.2, pullArm: 1.0, glare: 1.6, threat: 1.6, snap: 2.6, nod: 0.7, shake_head: 1.0, sigh: 2.4, tilt: 2.0,
      turn_away: 2.4, lookAround: 3.2, point: 1.6, shrug: 1.3, shiftWeight: 3 }[name] || 1;
    this.clips.push({ name, t0: this.t, dur, o });
  }
  _clipTargets(T) {
    const keep = [];
    for (const c of this.clips) {
      const p = (this.t - c.t0) / c.dur;
      if (p >= 1) continue;
      keep.push(c);
      const o = c.o, pw = o.power ?? 1, sd = o.side ?? 1;
      switch (c.name) {
        case 'flinch': { const e = env(p, 0.1, 0.75) * pw; T.chestP -= 0.09 * e; T.headP -= 0.12 * e; T.headY += sd * 0.16 * e; T.lid += 0.55 * e; T.hipX += sd * 0.01 * e; break; }
        case 'recoil': { const e = env(p, 0.1, 0.7) * pw; T.chestP -= 0.17 * e; T.headP -= 0.2 * e; T.hipX += sd * 0.025 * e; T.headY += sd * 0.22 * e; T.shL += 0.07 * e; T.shR += 0.07 * e; T.lid += 0.4 * e; T.hipZ -= 0.03 * e; break; }
        case 'pullArm': { const e = env(p, 0.12, 0.7), s = sd > 0 ? 'R' : 'L', g = sd > 0 ? 1 : -1; T['arm' + s + 'z'] += g * 0.4 * e; T['arm' + s + 'x'] -= 0.3 * e; T.chestY += g * 0.06 * e; T.headY += g * 0.1 * e; T.lid += 0.3 * e; break; }
        case 'glare': { const e = env(p, 0.15, 0.4); T.lid += 0.25 * e; T.tilt += 0.9 * e; T.headP += 0.08 * e; T.eyeContact = Math.max(T.eyeContact, e); break; }
        case 'threat': { const e = env(p, 0.2, 0.4); T.lean += 0.07 * e; T.shL += 0.08 * e; T.shR += 0.08 * e; T.armPose = 'threat'; T.armPoseW = Math.max(T.armPoseW, e); break; }
        case 'snap': { const e = env(p, 0.12, 0.5); T.headY += sd * 0.42 * e; T.chestY += sd * 0.3 * e; T.lid += 0.3 * e; T.tilt += 1.1 * e; T.shake += 1.0 * e; T.aura += 0.6 * e; T.armPose = 'threat'; T.armPoseW = Math.max(T.armPoseW, e); T.gx -= sd * 0.9 * e; break; }
        case 'nod': { const e = Math.sin(p * Math.PI * 2) * (1 - p) * pw; T.headP += 0.14 * e; T.chestP += 0.02 * e; break; }
        case 'shake_head': { const e = Math.sin(p * Math.PI * 4) * (1 - p); T.headY += 0.2 * e; T.chestY += 0.03 * e; break; }
        case 'tilt': { const e = env(p, 0.2, 0.4); T.headR += sd * 0.13 * e; T.headP -= 0.03 * e; break; }
        case 'sigh': { const e = Math.sin(p * Math.PI); T.chestP -= 0.03 * e; T.shL += 0.05 * e; T.shR += 0.05 * e; T.headP += 0.1 * Math.sin(Math.min(1, p * 1.6) * Math.PI); break; }
        case 'turn_away': { const e = env(p, 0.2, 0.3); T.headY += sd * 0.5 * e; T.chestY += sd * 0.22 * e; T.gx -= sd * 0.8 * e; T.lid += 0.15 * e; break; }
        case 'lookAround': { const e = Math.sin(p * Math.PI * 2); T.headY += 0.34 * e; T.gx += 0.7 * Math.sin(p * Math.PI * 2 + 0.5); T.gy += 0.1; break; }
        case 'point': { const e = env(p, 0.2, 0.3); T.armPose = 'speakR'; T.armPoseW = Math.max(T.armPoseW, e); T.headY += 0.1 * e; break; }
        case 'shrug': { const e = env(p, 0.2, 0.4); T.shL += 0.12 * e; T.shR += 0.12 * e; T.headR += 0.06 * e; T.headP += 0.03 * e; break; }
        case 'shiftWeight': { const e = env(p, 0.3, 0.3); T.hipX += sd * 0.02 * e; T.hipR += sd * 0.03 * e; break; }
        default: break;
      }
    }
    this.clips = keep;
  }

  // ctx: {state, out, mic, localOut, anger, level, sulking, cam:{yaw}, pointer:{x,y,age}}
  update(dt, ctx) {
    this.t += dt; const t = this.t;
    const T = { headP: 0, headY: 0, headR: 0, chestP: 0, chestY: 0, chestR: 0, hipX: 0, hipZ: 0, hipR: 0, lean: 0, shL: 0, shR: 0,
      lid: 0, tilt: 0, low: 0, smile: 0, mouth: 0, width: 0, gx: 0, gy: 0, armRx: 0, armRz: 0, armLx: 0, armLz: 0, shake: 0, aura: 0,
      eyeContact: 0, armPose: null, armPoseW: 0 };

    // always-on life: breathing, sway, micro head motion
    const br = Math.sin(t * 2 * Math.PI / 4.4);
    T.chestP += 0.010 * br; T.shL += 0.004 * br; T.shR += 0.004 * br; T.headP -= 0.006 * br;
    T.hipX += 0.009 * Math.sin(t * 0.31) + this.weight; T.hipR += 0.011 * Math.sin(t * 0.31 + 1) + this.weight * 1.2;
    T.headY += 0.045 * noise(t * 0.6, 1); T.headP += 0.022 * noise(t * 0.5, 2); T.headR += 0.02 * noise(t * 0.4, 3);
    this.weight = damp(this.weight, this.weightT, 1.2, dt);

    // who is she looking at? the camera (you), your pointer, or wandering
    const g = this.gaze;
    if (t > g.next) { g.tx = (Math.random() - 0.5) * 1.0; g.ty = (Math.random() - 0.5) * 0.45; g.next = t + 0.9 + Math.random() * 2.6; }
    let gx = g.tx * 0.6, gy = g.ty * 0.6, look = 0.25;
    const cy = clamp(ctx.cam ? ctx.cam.yaw : 0, -0.7, 0.7);
    if (ctx.pointer && ctx.pointer.age < 3) { gx = clamp(ctx.pointer.x, -1, 1) * 0.9; gy = clamp(-ctx.pointer.y, -1, 1) * 0.5; look = 0.45; }
    T.headY += cy * look; T.gx += gx + cy * 0.5; T.gy += gy;

    // Trilion's state
    const st = ctx.state;
    if (st === 'listening') { T.headR += 0.06; T.chestP += 0.015; T.lean += 0.02; T.eyeContact = 0.7; T.headY += cy * 0.3; if (ctx.mic > 0.35 && this.nodCool < t) { this.play('nod', { power: 0.6 }); this.nodCool = t + 1.4; } }
    else if (st === 'thinking') { T.gx -= 0.7; T.gy += 0.5; T.headY -= 0.14; T.headP -= 0.05; T.lid += 0.06; this.poseArms('front', 1.2); }
    else if (st === 'acting') { T.gy -= 0.35; T.gx -= 0.4; T.headP += 0.05; T.lid += 0.1; }
    else if (st === 'speaking') {
      T.eyeContact = 0.6;
      if (ctx.out - this.lastOut > 0.18 && this.nodCool < t) { this.play('nod', { power: 0.5 }); this.nodCool = t + 0.9; }
      T.headY += 0.05 * Math.sin(t * 1.7); T.headP += 0.02 * Math.sin(t * 2.3);
      if (t > this.speakGestureNext) { this.poseArms(['speakL', 'speakR', 'explain', 'front2'][Math.floor(Math.random() * 4)], 1.5 + Math.random()); this.speakGestureNext = t + 2.5 + Math.random() * 2.5; }
    } else if (!this.clips.length && t > this.idleNext) this._idleAction();
    this.lastOut = damp(this.lastOut, ctx.out, 0.08, dt);

    // mouth: lip-sync to Trilion's voice (or to a stock line playing in the page)
    const lvl = Math.max(st === 'speaking' ? ctx.out : 0, ctx.localOut || 0);
    if (lvl > 0.02) { T.mouth = clamp(lvl * 2.6, 0, 1) * (0.72 + 0.28 * Math.sin(t * 24)); T.width = 0.5 * Math.sin(t * 9.5); }

    // mood / emotion
    const em = EMOTIONS[t < this.emotionUntil ? this.emotion : (ctx.level && ctx.level !== 'calm' ? ctx.level : 'neutral')] || EMOTIONS.neutral;
    const a = ctx.anger || 0;
    T.lid += em.lid + 0.1 * a; T.tilt += em.tilt; T.low += em.low; T.smile += em.smile; T.headP += em.headP; T.lean += em.lean; T.headR += em.headR || 0;
    T.aura += a; T.shL += 0.07 * a; T.shR += 0.07 * a;
    if (a > 0.7) T.shake += (a - 0.7) * 1.4;
    if (ctx.sulking) { T.headY += this.sulkSide * 0.42; T.chestY += this.sulkSide * 0.24; T.gx -= this.sulkSide * 0.9; T.lid += 0.15; this.poseArms('front2', 0.5); }

    this._clipTargets(T);

    // smoothing
    const hl = { lid: 0.045, mouth: 0.045, width: 0.06, gx: 0.07, gy: 0.07, tilt: 0.09, low: 0.12, smile: 0.2, shake: 0.1, aura: 0.25, eyeContact: 0.15 };
    const C = this.ch;
    for (const k of Object.keys(T)) { if (k === 'armPose' || k === 'armPoseW') continue; C[k] = damp(C[k] ?? 0, T[k], hl[k] || 0.13, dt); }

    // arm pose blending
    let want = t < this.armHold ? this.armTo : 'hang';
    if (T.armPose) want = T.armPose;
    if (want === 'hang' && st === 'idle' && t > this.armHold && Math.sin(t * 0.05) > 0.55) want = 'front';
    const goal = ARM_POSES[want];
    for (const k of ARM_KEYS) for (let i = 0; i < 3; i++) this.arm[k][i] = damp(this.arm[k][i], goal[k][i], T.armPose ? 0.12 : 0.3, dt);

    // blink scheduler
    const bl = this.blink;
    if (bl.t < 0 && t > bl.next) { bl.t = 0; bl.dbl = Math.random() < 0.15; }
    let blinkV = 0;
    if (bl.t >= 0) { bl.t += dt; const u = bl.t / 0.24; blinkV = u < 0.3 ? u / 0.3 : u < 0.45 ? 1 : Math.max(0, 1 - (u - 0.45) / 0.55); if (u >= 1) { bl.t = -1; bl.next = t + (bl.dbl ? 0.18 : 2.2 + Math.random() * 3.6); bl.dbl = false; } }

    this._apply(C, blinkV, dt);
  }

  _idleAction() {
    const p = Math.random();
    if (p < 0.28) this.play('lookAround');
    else if (p < 0.5) this.play('tilt', { side: Math.random() < 0.5 ? -1 : 1 });
    else if (p < 0.65) this.play('sigh');
    else if (p < 0.8) { this.weightT = (Math.random() - 0.5) * 0.04; this.play('shiftWeight', { side: Math.sign(this.weightT) || 1 }); }
    else if (p < 0.9) this.poseArms('front', 5 + Math.random() * 4);
    else this.play('shrug');
    this.idleNext = this.t + 6 + Math.random() * 8;
  }

  _apply(C, blinkV, dt) {
    const r = this.A.rig, fp = this.A.fp, t = this.t;
    const sh = C.shake * 0.012, tx = sh * Math.sin(t * 47), ty = sh * Math.sin(t * 39 + 1);
    r.rot(B.hips, 0, C.chestY * 0.15, C.hipR); r.moveWorld(B.hips, C.hipX, 0, C.hipZ);
    r.rot(B.spine1, C.lean * 0.4 + C.chestP * 0.25, C.chestY * 0.25, -C.hipR * 0.6);
    r.rot(B.spine2, C.lean * 0.35 + C.chestP * 0.35, C.chestY * 0.3, -C.hipR * 0.3);
    r.rot(B.chest, C.lean * 0.25 + C.chestP * 0.4, C.chestY * 0.35 + tx * 0.3, C.chestR);
    r.rot(B.neck, C.headP * 0.35, C.headY * 0.35, C.headR * 0.35);
    r.rot(B.head, C.headP * 0.65 + ty, C.headY * 0.65 + tx, C.headR * 0.65);
    r.move(B.clavL, 0, C.shL * 0.5, 0); r.move(B.clavR, 0, C.shR * 0.5, 0);
    r.rot(B.clavL, 0, 0, -C.shL * 0.5); r.rot(B.clavR, 0, 0, C.shR * 0.5);
    for (const k of ARM_KEYS) r.rot(B[k], this.arm[k][0], this.arm[k][1], this.arm[k][2]);
    r.rot(B.armR, C.armRx, 0, C.armRz); r.rot(B.armL, C.armLx, 0, C.armLz);
    r.rot(B.armR, 0, 0, 0.008 * Math.sin(t * 1.3)); r.rot(B.armL, 0, 0, -0.008 * Math.sin(t * 1.3 + 1));
    const lid = clamp(Math.max(blinkV, C.lid), 0, 1);
    for (const e of ['lidL', 'lidR']) { fp[e].closed = lid; fp[e].tilt = C.tilt; fp[e].low = clamp(C.low + C.smile * 0.3, 0, 1); }
    fp.mouth.open = clamp(C.mouth, 0, 1); fp.mouth.width = C.width; fp.mouth.smile = C.smile;
    fp.gaze.x = clamp(C.gx, -1, 1); fp.gaze.y = clamp(C.gy, -1, 1);
    this.jig.update(dt, { hipX: C.hipX, headY: C.headY, chestP: C.chestP, t, shake: C.shake });
  }
}

// Hair / coat / sleeve physics: a damped spring lags behind body motion (plus a breath of wind). Every bone in a chain
// adds a small swing, so the tip moves most. Gentle and symmetric: it should read as cloth, not flailing.
export class Jiggle {
  constructor(rig) {
    this.rig = rig; this.v = { x: 0, z: 0 }; this.p = { x: 0, z: 0 }; this.prev = { hipX: 0, headY: 0 };
    this.groups = [];
    for (const n of Object.keys(rig.bones)) {
      if (!n.startsWith('+') || /Eye|Tooth|Breast|Twist|_end$/.test(n)) continue;
      this.groups.push({ n, k: /Hair/.test(n) ? 0.55 : /Skirt/.test(n) ? 0.5 : /Sleeve/.test(n) ? 0.3 : 0.25, ph: (n.length * 7.7) % 6.28 });
    }
  }
  update(dt, s) {
    dt = Math.max(dt, 1e-3);
    const vx = clamp((s.hipX - this.prev.hipX) / dt, -0.3, 0.3), vy = clamp((s.headY - this.prev.headY) / dt, -2, 2);
    this.prev = { hipX: s.hipX, headY: s.headY };
    const tx = -vx * 2.0 - vy * 0.12, tz = 0.25 * Math.sin(s.t * 1.1) - s.chestP * 3, h = Math.min(dt, 0.03);
    for (let i = 0; i < Math.ceil(dt / h); i++) {
      this.v.x += ((tx - this.p.x) * 40 - this.v.x * 7) * h; this.p.x += this.v.x * h;
      this.v.z += ((tz - this.p.z) * 40 - this.v.z * 7) * h; this.p.z += this.v.z * h;
    }
    const wx = clamp(this.p.x, -1, 1) * 0.5 + (s.shake ? 0.1 * Math.sin(s.t * 31) * s.shake : 0), wz = clamp(this.p.z, -1, 1) * 0.35;
    for (const g of this.groups) {
      const w = 0.1 * Math.sin(s.t * 1.7 + g.ph);
      this.rig.rot(g.n, (wz + w * 0.5) * g.k * 0.1, 0, (-wx + w) * g.k * 0.1);
    }
  }
}
