// Animator: always-on idle life + state behaviours + emotions + one-shot clips (reactions, gestures) + hair/coat physics.
// Nothing here waits for the AI: every channel eases toward its target, so she is never frozen or popping.
import { B } from './rig.js';
import { clamp, damp, ease, envS, Breath, Gaze, Lipsync, ChainSim } from './motion.js';
export const noise = (t, s = 0) => (Math.sin(t + s * 12.9) + 0.6 * Math.sin(t * 2.3 + s * 7.1) + 0.8 * Math.sin(t * 0.37 + s * 3.3)) / 2.4;

export const ARM_POSES = {
  hang: { armR: [0, 0, 0.5], armL: [0, 0, -0.5], foreR: [-0.2, 0, 0], foreL: [-0.2, 0, 0] },
  front: { armR: [-0.35, 0, 0.45], armL: [-0.35, 0, -0.45], foreR: [-1.15, 0, 0], foreL: [-1.15, 0, 0] },
  front2: { armR: [-0.5, 0.25, 0.35], armL: [-0.5, -0.25, -0.35], foreR: [-1.3, 0.3, 0], foreL: [-1.3, -0.3, 0] },
  speakL: { armR: [0, 0, 0.5], armL: [-0.55, 0, -0.3], foreR: [-0.2, 0, 0], foreL: [-1.45, 0, 0] },
  speakR: { armR: [-0.55, 0, 0.3], armL: [0, 0, -0.5], foreR: [-1.45, 0, 0], foreL: [-0.2, 0, 0] },
  explain: { armR: [-1.0, 0.2, 0.1], armL: [0, 0, -0.5], foreR: [-1.9, 0, 0], foreL: [-0.2, 0, 0] },
  threat: { armR: [-0.55, 0.55, 0.3], armL: [-0.55, -0.55, -0.3], foreR: [-1.5, 0.7, 0], foreL: [-1.5, -0.7, 0] },
  // signature poses
  crossed: { armR: [-0.9, 0.5, 0.35], armL: [-1.05, -0.5, -0.35], foreR: [-1.1, 1.2, 0.3], foreL: [-1.1, -1.2, 0] },
  chin: { armR: [-0.7, 0.9, 0.1], armL: [-0.9, -0.5, -0.35], foreR: [-2.0, 0.9, 0], foreL: [-1.1, -1.2, 0] },
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
export const GESTURES = ['none', 'nod', 'shake_head', 'glare', 'turn_away', 'sigh', 'point', 'tilt', 'shrug', 'cross_arms', 'chin', 'dismiss'];
// per clip: default length, fade-in / fade-out seconds, and a group (a new clip releases older ones of its group over 0.28 s, so nothing pops or stacks up)
export const CLIPS = {
  flinch: { dur: 0.9, a: 0.07, r: 0.7, g: 'startle' }, recoil: { dur: 1.2, a: 0.09, r: 0.9, g: 'startle' }, snap: { dur: 2.6, a: 0.12, r: 1.2, g: 'startle' },
  threat: { dur: 1.6, a: 0.3, r: 0.6, g: 'startle' }, pullArm: { dur: 1.0, a: 0.12, r: 0.6, g: 'arm' },
  glare: { dur: 1.6, a: 0.25, r: 0.6, g: 'gaze' }, turn_away: { dur: 2.4, a: 0.45, r: 0.7, g: 'gaze' }, lookAround: { dur: 3.2, a: 0.4, r: 0.5, g: 'gaze' },
  nod: { dur: 0.7, a: 0.1, r: 0.3, g: 'head' }, shake_head: { dur: 1.0, a: 0.1, r: 0.3, g: 'head' }, beat: { dur: 0.45, a: 0.08, r: 0.3, g: 'beat' }, tilt: { dur: 2.0, a: 0.4, r: 0.8, g: 'head' },
  sigh: { dur: 2.4, a: 0.6, r: 1.0, g: 'breath' }, shrug: { dur: 1.3, a: 0.25, r: 0.5, g: 'shoulder' }, point: { dur: 1.6, a: 0.3, r: 0.5, g: 'armpose' },
  shiftWeight: { dur: 3, a: 0.9, r: 0.9, g: 'weight' }, cross_arms: { dur: 4.5, a: 0.6, r: 0.7, g: 'armpose' }, chin: { dur: 4, a: 0.6, r: 0.7, g: 'armpose' }, dismiss: { dur: 1.5, a: 0.18, r: 0.5, g: 'armpose' },
};

export class Animator {
  constructor(A) {
    this.A = A; this.t = 0;
    this.ch = {}; this.clips = []; this.arm = {}; this.armHold = 0; this.armTo = 'hang';
    for (const k of ARM_KEYS) this.arm[k] = [...ARM_POSES.hang[k]];
    this.breath = new Breath(); this.eyes = new Gaze(); this.lip = new Lipsync(); this.shift = { cur: 0, tgt: 0, next: 5 };
    this.blink = { t: -1, next: 2.5, dbl: false };
    this.intensity = 1; this.quality = 0; this.prevState = 'idle'; this.beatCool = 0; this.typeNod = 0; this.lastCtx = {};
    this.idleNext = 7; this.speakGestureNext = 2; this.lastOut = 0; this.nodCool = 0;
    this.emotion = 'neutral'; this.emotionUntil = 0; this.sulkSide = 1; this.jig = new Jiggle(A.rig);
  }
  setEmotion(name, secs = 4) { if (EMOTIONS[name]) { this.emotion = name; this.emotionUntil = this.t + secs; } }
  poseArms(name, secs = 2.5) { if (ARM_POSES[name]) { this.armTo = name; this.armHold = this.t + secs; } }
  play(name, o = {}) {
    const d = CLIPS[name] || { dur: 1, a: 0.2, r: 0.5, g: 'misc' }, dur = o.dur || d.dur;
    for (const c of this.clips) if (c.g === d.g && d.g !== 'misc' && c.kill === null) c.kill = this.t;   // older clips of the same group release smoothly
    this.clips.push({ name, t0: this.t, dur, a: d.a, r: d.r, g: d.g, o, kill: null });
  }
  _clipTargets(T, anger) {
    const keep = [];
    for (const c of this.clips) {
      const age = this.t - c.t0;
      if (age >= c.dur) continue;
      let w = 1;
      if (c.kill !== null) { w = 1 - ease((this.t - c.kill) / 0.28); if (w <= 0) continue; }
      keep.push(c);
      const o = c.o, p = age / c.dur, pw = (o.power ?? 1) * (1 + 0.5 * anger) * w, sd = o.side ?? 1, z = o.zone || '';
      const e = envS(age, c.dur, c.a, c.r) * pw;
      switch (c.name) {
        case 'flinch': {
          const head = z === 'head' || z === 'face' || z === 'hair', body = z === 'chest' || z === 'belly', limb = z === 'arm' || z === 'hand', back = z === 'back';
          T.chestP -= (body ? 0.14 : 0.09) * e; T.headP -= (head ? 0.18 : 0.12) * e; T.headY += sd * (back ? 0.3 : 0.16) * e; T.lid += 0.55 * e; T.hipX += sd * 0.01 * e;
          if (limb) { T.chestY += sd * 0.1 * e; T.shL += (sd < 0 ? 0.1 : 0.02) * e; T.shR += (sd > 0 ? 0.1 : 0.02) * e; }
          if (back) { T.chestY += sd * 0.2 * e; T.gx += sd * 0.5 * e; }
          break;
        }
        case 'recoil': { T.chestP -= 0.17 * e; T.headP -= 0.2 * e; T.hipX += sd * 0.025 * e; T.headY += sd * 0.22 * e; T.shL += 0.07 * e; T.shR += 0.07 * e; T.lid += 0.4 * e; T.hipZ -= 0.03 * e; break; }
        case 'pullArm': { const s2 = sd > 0 ? 'R' : 'L', g = sd > 0 ? 1 : -1; T['arm' + s2 + 'z'] += g * 0.4 * e; T['arm' + s2 + 'x'] -= 0.3 * e; T.chestY += g * 0.06 * e; T.headY += g * 0.1 * e; T.lid += 0.3 * e; break; }
        case 'glare': { T.lid += 0.25 * e; T.tilt += 0.9 * e; T.headP += 0.08 * e; T.eyeContact = Math.max(T.eyeContact, e); break; }
        case 'threat': { T.lean += 0.07 * e; T.shL += 0.08 * e; T.shR += 0.08 * e; T.armPose = 'threat'; T.armPoseW = Math.max(T.armPoseW, e); break; }
        case 'snap': { T.headY += sd * 0.42 * e; T.chestY += sd * 0.3 * e; T.lid += 0.3 * e; T.tilt += 1.1 * e; T.shake += 1.0 * e; T.aura += 0.6 * e; T.armPose = 'threat'; T.armPoseW = Math.max(T.armPoseW, e); T.gx -= sd * 0.9 * e; break; }
        case 'nod': { const k = Math.sin(p * Math.PI * 2) * (1 - p) * pw; T.headP += 0.14 * k; T.chestP += 0.02 * k; break; }
        case 'shake_head': { const k = Math.sin(p * Math.PI * 4) * (1 - p) * pw; T.headY += 0.2 * k; T.chestY += 0.03 * k; break; }
        case 'beat': { T.headP += 0.055 * e; T.chestP += 0.012 * e; T.shL += 0.02 * e; T.shR += 0.02 * e; T.armRx -= 0.1 * e * (sd > 0 ? 1 : 0.4); T.armLx -= 0.1 * e * (sd > 0 ? 0.4 : 1); break; }
        case 'tilt': { T.headR += sd * 0.13 * e; T.headP -= 0.03 * e; break; }
        case 'sigh': { const k = Math.sin(p * Math.PI) * pw; T.chestP -= 0.03 * k; T.shL += 0.05 * k; T.shR += 0.05 * k; T.headP += 0.1 * Math.sin(Math.min(1, p * 1.6) * Math.PI) * pw; if (p > 0.45 && !c.deep) { c.deep = true; this.breath.deepen(); } break; }
        case 'turn_away': { T.headY += sd * 0.5 * e; T.chestY += sd * 0.22 * e; T.gx -= sd * 0.8 * e; T.lid += 0.15 * e; break; }
        case 'lookAround': { const k = Math.sin(p * Math.PI * 2) * w; T.headY += 0.34 * k; T.gx += 0.7 * Math.sin(p * Math.PI * 2 + 0.5) * w; T.gy += 0.1 * w; break; }
        case 'point': { T.armPose = 'speakR'; T.armPoseW = Math.max(T.armPoseW, e); T.headY += 0.1 * e; break; }
        case 'shrug': { T.shL += 0.12 * e; T.shR += 0.12 * e; T.headR += 0.06 * e; T.headP += 0.03 * e; break; }
        case 'shiftWeight': { this.shift.tgt = sd * 0.8; break; }
        case 'cross_arms': { T.armPose = 'crossed'; T.armPoseW = Math.max(T.armPoseW, e); T.shL += 0.04 * e; T.shR += 0.04 * e; T.headP += 0.03 * e; T.tilt += 0.3 * e; T.lid += 0.1 * e; break; }
        case 'chin': { T.armPose = 'chin'; T.armPoseW = Math.max(T.armPoseW, e); T.headR += 0.09 * e; T.headP += 0.03 * e; T.gx -= 0.5 * e; T.gy += 0.3 * e; T.headY -= 0.1 * e; break; }
        case 'dismiss': { T.armPose = 'speakR'; T.armPoseW = Math.max(T.armPoseW, e); T.handRz += Math.sin(p * Math.PI * 6) * 0.45 * e * (p > 0.25 ? 1 : 0); T.headY += 0.18 * e; T.gx -= 0.5 * e; T.lid += 0.2 * e; T.tilt += 0.4 * e; break; }
        default: break;
      }
    }
    this.clips = keep;
  }

  // ctx: {state, out, mic, localOut, spec, typing, anger, level, sulking, cam:{yaw}, pointer:{x,y,age}}
  update(dt, ctx) {
    this.t += dt; const t = this.t; this.lastCtx = ctx;
    const st = ctx.state, anger = ctx.anger || 0;
    const T = { headP: 0, headY: 0, headR: 0, chestP: 0, chestY: 0, chestR: 0, hipX: 0, hipZ: 0, hipR: 0, lean: 0, shL: 0, shR: 0,
      lid: 0, tilt: 0, low: 0, smile: 0, mouth: 0, width: 0, gx: 0, gy: 0, armRx: 0, armRz: 0, armLx: 0, armLz: 0, handRz: 0, shake: 0, aura: 0,
      eyeContact: 0, armPose: null, armPoseW: 0 };

    // always-on life: an asymmetric breath (quick in, slow out, pause), a slow weight shift with counter-balance, micro head motion
    const arousal = clamp(anger * 0.8 + (st === 'speaking' ? 0.3 : 0) + ((ctx.mic || 0) > 0.3 ? 0.2 : 0), 0, 1);
    const br = this.breath.update(dt, arousal);
    T.chestP += 0.013 * br; T.shL += 0.005 * br; T.shR += 0.005 * br; T.headP -= 0.007 * br; T.lean += 0.004 * br; T.armRx += 0.004 * br; T.armLx += 0.004 * br;
    const S = this.shift;
    if (t > S.next) { S.tgt = Math.random() < 0.25 ? 0 : (Math.random() - 0.5) * 1.6; S.next = t + 6 + Math.random() * 8; }
    S.cur = damp(S.cur, S.tgt, 1.4, dt);
    T.hipX += 0.006 * Math.sin(t * 0.31) + S.cur * 0.02; T.hipR += 0.008 * Math.sin(t * 0.31 + 1) + S.cur * 0.035;
    T.chestR -= S.cur * 0.02; T.headR -= S.cur * 0.015; T.shL += Math.max(0, S.cur) * 0.015; T.shR += Math.max(0, -S.cur) * 0.015;
    T.headY += 0.04 * noise(t * 0.6, 1); T.headP += 0.02 * noise(t * 0.5, 2); T.headR += 0.018 * noise(t * 0.4, 3);

    // eyes lead, head follows: the camera (you), your pointer, the chat box while you type, or wandering fixations
    const cy = clamp(ctx.cam ? ctx.cam.yaw : 0, -0.7, 0.7), typing = (ctx.typing || 0) > 0;
    let o = { w: 0 }, look = 0.25;
    if (ctx.pointer && ctx.pointer.age < 3) { o = { x: clamp(ctx.pointer.x, -1, 1) * 0.9, y: clamp(-ctx.pointer.y, -1, 1) * 0.5, w: 1 }; look = 0.45; }
    else if (typing) o = { x: 0, y: -0.45, w: 1 };
    const ey = this.eyes.update(dt, t, o);
    T.gx += ey.ex + cy * 0.5; T.gy += ey.ey; T.headY += ey.hx * 0.3 + cy * look; T.headP -= ey.hy * 0.2;
    if (ey.jump > 0.35 && this.blink.t < 0 && Math.random() < 0.55) { this.blink.t = 0; this.blink.dbl = false; }   // we blink with big gaze shifts

    // Trilion's state
    if (st === 'listening') { T.headR += 0.06; T.chestP += 0.015; T.lean += 0.02; T.eyeContact = 0.7; T.headY += cy * 0.3; if (ctx.mic > 0.35 && this.nodCool < t) { this.play('nod', { power: 0.6 }); this.nodCool = t + 1.4; } }
    else if (st === 'thinking') { T.gx -= 0.7; T.gy += 0.5; T.headY -= 0.14; T.headP -= 0.05; T.lid += 0.06; this.poseArms(anger > 0.3 ? 'front' : 'chin', 1.2); }
    else if (st === 'acting') { T.gy -= 0.35; T.gx -= 0.4; T.headP += 0.05; T.lid += 0.1; }
    else if (st === 'speaking') {
      T.eyeContact = 0.6;
      if (ctx.out - this.lastOut > 0.18 && this.nodCool < t) { this.play('nod', { power: 0.5 }); this.nodCool = t + 0.9; }
      T.headY += 0.05 * Math.sin(t * 1.7); T.headP += 0.02 * Math.sin(t * 2.3);
      if (t > this.speakGestureNext) { this.poseArms(['speakL', 'speakR', 'explain', 'front2'][Math.floor(Math.random() * 4)], 1.5 + Math.random()); this.speakGestureNext = t + 2.5 + Math.random() * 2.5; }
    } else if (typing) {                                      // listening to you type: head down toward the box, an occasional nod
      T.headR += 0.05; T.headP += 0.05; T.eyeContact = 0.5; T.lean += 0.015;
      if (t > this.typeNod) { this.play('nod', { power: 0.4 }); this.typeNod = t + 2.5 + Math.random() * 2; }
    } else if (!this.clips.length && t > this.idleNext) this._idleAction(ctx);
    if (this.prevState === 'speaking' && st !== 'speaking' && this.blink.t < 0) this.blink.t = 0;   // blink when she finishes a sentence
    this.prevState = st;
    this.lastOut = damp(this.lastOut, ctx.out, 0.08, dt);

    // mouth: syllable lip-sync to Trilion's voice (or a stock line playing in the page); loud peaks trigger emphasis beats
    const lvl = Math.max(st === 'speaking' ? ctx.out : 0, ctx.localOut || 0);
    const L = this.lip.update(dt, lvl, (ctx.localOut || 0) > 0.02 && ctx.spec != null ? ctx.spec : -1);
    T.mouth = L.open; T.width = L.width;
    if (L.beat && this.beatCool < t) { this.play('beat', { power: 0.8 + Math.random() * 0.5, side: Math.random() < 0.5 ? -1 : 1 }); this.beatCool = t + 0.55; }

    // mood / emotion
    const em = EMOTIONS[t < this.emotionUntil ? this.emotion : (ctx.level && ctx.level !== 'calm' ? ctx.level : 'neutral')] || EMOTIONS.neutral;
    T.lid += em.lid + 0.1 * anger; T.tilt += em.tilt; T.low += em.low; T.smile += em.smile; T.headP += em.headP; T.lean += em.lean; T.headR += em.headR || 0;
    T.aura += anger; T.shL += 0.07 * anger; T.shR += 0.07 * anger;
    if (anger > 0.7) T.shake += (anger - 0.7) * 1.4;
    if (ctx.sulking) { T.headY += this.sulkSide * 0.42; T.chestY += this.sulkSide * 0.24; T.gx -= this.sulkSide * 0.9; T.lid += 0.15; this.poseArms('crossed', 0.5); }

    this._clipTargets(T, anger);

    // smoothing
    const hl = { lid: 0.045, mouth: 0.012, width: 0.02, gx: 0.07, gy: 0.07, tilt: 0.09, low: 0.12, smile: 0.2, shake: 0.1, aura: 0.25, eyeContact: 0.15, handRz: 0.05 };
    const C = this.ch;
    for (const k of Object.keys(T)) { if (k === 'armPose' || k === 'armPoseW') continue; C[k] = damp(C[k] ?? 0, T[k], hl[k] || 0.13, dt); }

    // arm pose blending
    let want = t < this.armHold ? this.armTo : 'hang';
    if (T.armPose) want = T.armPose;
    if (want === 'hang' && st === 'idle' && t > this.armHold && Math.sin(t * 0.05) > 0.55) want = 'front';
    const goal = ARM_POSES[want];
    for (const k of ARM_KEYS) for (let i = 0; i < 3; i++) this.arm[k][i] = damp(this.arm[k][i], goal[k][i], T.armPose ? 0.14 : 0.3, dt);

    // blink scheduler: slower while glaring/angry, quicker while thinking
    const bl = this.blink;
    if (bl.t < 0 && t > bl.next) { bl.t = 0; bl.dbl = Math.random() < 0.15; }
    let blinkV = 0;
    if (bl.t >= 0) { bl.t += dt; const u = bl.t / 0.24; blinkV = u < 0.3 ? u / 0.3 : u < 0.45 ? 1 : Math.max(0, 1 - (u - 0.45) / 0.55);
      if (u >= 1) { bl.t = -1; bl.next = t + (bl.dbl ? 0.18 : (2.2 + Math.random() * 3.6) * (st === 'thinking' ? 0.65 : 1) * (1 + 0.9 * anger)); bl.dbl = false; } }

    this._apply(C, blinkV, dt);
  }

  _idleAction(ctx = {}) {
    const p = Math.random(), mood = ctx.level && ctx.level !== 'calm';
    if (mood && p < 0.4) this.play('cross_arms');
    else if (p < 0.28) this.play('lookAround');
    else if (p < 0.5) this.play('tilt', { side: Math.random() < 0.5 ? -1 : 1 });
    else if (p < 0.65) this.play('sigh');
    else if (p < 0.8) this.play('shiftWeight', { side: Math.random() < 0.5 ? -1 : 1 });
    else if (p < 0.9) this.poseArms('front', 5 + Math.random() * 4);
    else if (p < 0.95) this.play('chin');
    else this.play('shrug');
    this.idleNext = this.t + 6 + Math.random() * 8;
  }

  _apply(C0, blinkV, dt) {
    const r = this.A.rig, fp = this.A.fp, t = this.t, I = this.intensity, hang = ARM_POSES.hang;
    const C = Object.assign({}, C0);                          // motion-intensity slider scales every body rotation (not eyes, mouth, aura)
    for (const k of ['headP', 'headY', 'headR', 'chestP', 'chestY', 'chestR', 'hipX', 'hipZ', 'hipR', 'lean', 'shL', 'shR', 'armRx', 'armRz', 'armLx', 'armLz', 'handRz']) C[k] = (C0[k] || 0) * I;
    const sh = C.shake * 0.012, tx = sh * Math.sin(t * 47), ty = sh * Math.sin(t * 39 + 1);
    r.rot(B.hips, 0, C.chestY * 0.15, C.hipR); r.moveWorld(B.hips, C.hipX, 0, C.hipZ);
    r.rot(B.spine1, C.lean * 0.4 + C.chestP * 0.25, C.chestY * 0.25, -C.hipR * 0.6);
    r.rot(B.spine2, C.lean * 0.35 + C.chestP * 0.35, C.chestY * 0.3, -C.hipR * 0.3);
    r.rot(B.chest, C.lean * 0.25 + C.chestP * 0.4, C.chestY * 0.35 + tx * 0.3, C.chestR);
    r.rot(B.neck, C.headP * 0.35, C.headY * 0.35, C.headR * 0.35);
    r.rot(B.head, C.headP * 0.65 + ty, C.headY * 0.65 + tx, C.headR * 0.65);
    r.move(B.clavL, 0, C.shL * 0.5, 0); r.move(B.clavR, 0, C.shR * 0.5, 0);
    r.rot(B.clavL, 0, 0, -C.shL * 0.5); r.rot(B.clavR, 0, 0, C.shR * 0.5);
    for (const k of ARM_KEYS) { const a = this.arm[k]; r.rot(B[k], hang[k][0] + (a[0] - hang[k][0]) * I, hang[k][1] + (a[1] - hang[k][1]) * I, hang[k][2] + (a[2] - hang[k][2]) * I); }
    r.rot(B.armR, C.armRx, 0, C.armRz); r.rot(B.armL, C.armLx, 0, C.armLz);
    r.rot(B.armR, 0, 0, 0.008 * Math.sin(t * 1.3)); r.rot(B.armL, 0, 0, -0.008 * Math.sin(t * 1.3 + 1));
    if (C.handRz) r.rot(B.handR, 0, 0, C.handRz);
    const lid = clamp(Math.max(blinkV, C.lid), 0, 1);
    for (const e of ['lidL', 'lidR']) { fp[e].closed = lid; fp[e].tilt = C.tilt; fp[e].low = clamp(C.low + C.smile * 0.3, 0, 1); }
    fp.mouth.open = clamp(C.mouth, 0, 1); fp.mouth.width = C.width; fp.mouth.smile = C.smile;
    fp.gaze.x = clamp(C.gx, -1, 1); fp.gaze.y = clamp(C.gy, -1, 1);
    this.jig.update(dt, { hipX: C.hipX, headY: C.headY, chestP: C.chestP, t, shake: C.shake }, this.quality);
  }
}

// Hair / coat / sleeve physics: every bone is its own damped spring (looser toward the tip, so chains whip and trail), driven by body motion
// plus a breath of wind, with a soft one-sided limit so strands and cloth do not swing into the body. See motion.js ChainSim.
export class Jiggle {
  constructor(rig) {
    this.rig = rig; this.skip = false;
    const sp = rig.bones[B.spine2] && rig.bones[B.spine2][0], cz = sp ? sp.getWorldPosition(new sp.position.constructor()).z : 0;
    const ent = [], v = sp ? new sp.position.constructor() : null;
    for (const n of Object.keys(rig.bones)) {
      if (!n.startsWith('+') || /Eye|Tooth|Breast|Twist|_end$/.test(n)) continue;
      let side = 0, zsign = 0;
      if (v) { rig.bones[n][0].getWorldPosition(v); if (Math.abs(v.x) > 0.04) side = Math.sign(v.x); if (Math.abs(v.z - cz) > 0.04) zsign = v.z < cz ? 1 : -1; }
      ent.push({ name: n, side, zsign });
    }
    this.sim = new ChainSim(ent);
  }
  update(dt, s, quality = 0) {
    if (quality > 0) { this.skip = !this.skip; if (this.skip) return; dt *= 2; }   // low frame rate: simulate every other frame
    for (const b of this.sim.step(dt, s)) this.rig.rot(b.name, b.rx, 0, b.rz);
  }
}
