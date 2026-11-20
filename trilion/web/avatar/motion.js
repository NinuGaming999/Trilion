// Motion building blocks (pure maths, no THREE): breathing, eye/head gaze, lip-sync, text-driven gestures, spring chains for
// hair/cloth, and a frame-rate watchdog. Kept separate from anim.js so every piece can be unit-tested in node.
export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const damp = (cur, tgt, hl, dt) => cur + (tgt - cur) * (1 - Math.pow(2, -dt / hl));
export const ease = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const sstep = (a, b, x) => ease((x - a) / (b - a));

// Asymmetric breath: quick inhale, long exhale, short pause. Returns lung fullness 0..1.
export function breathCurve(p) {
  p -= Math.floor(p);
  if (p < 0.38) return sstep(0, 0.38, p);
  if (p < 0.88) return 1 - sstep(0.38, 0.88, p);
  return 0;
}
export class Breath {
  constructor(rnd = Math.random) { this.p = rnd(); this.t = 0; this.depth = 1; }
  update(dt, arousal = 0) {
    this.t += dt; const a = clamp(arousal, 0, 1);
    const period = (4.4 - 1.3 * a) * (1 + 0.1 * Math.sin(this.t * 0.21) + 0.06 * Math.sin(this.t * 0.53 + 1));
    this.p = (this.p + dt / period) % 1;
    this.depth = damp(this.depth, 1 + 0.6 * a, 1.5, dt);
    return (breathCurve(this.p) - 0.42) * this.depth;      // roughly -0.42 .. +0.58
  }
  deepen() { this.depth = 2.2; }                           // after a sigh
}

// Seconds-based clip envelope: fade in over `a`, hold, fade out over `r` (never longer than the clip).
export function envS(age, dur, a = 0.2, r = 0.5) {
  if (age < 0 || age >= dur) return 0;
  a = Math.max(1e-3, Math.min(a, dur * 0.5)); r = Math.max(1e-3, Math.min(r, dur - a));
  return ease(Math.min(age / a, (dur - age) / r, 1));
}

// Eyes lead, head follows: eyes snap (saccade) to a new fixation target, the head drifts after them a moment later.
// All values in "eye units" (about +-1 = full eye travel). A big jump is reported so the caller can blink with it.
export class Gaze {
  constructor(rnd = Math.random) { this.r = rnd; this.tx = 0; this.ty = 0; this.ex = 0; this.ey = 0; this.hx = 0; this.hy = 0; this.next = 0; this.mnext = 0; this.mx = 0; this.my = 0; }
  update(dt, t, o = {}) {
    let jump = 0;
    if ((o.w || 0) > 0.35) {                                // looking at something specific (pointer, chat box)
      const nx = o.x || 0, ny = o.y || 0; jump = Math.hypot(nx - this.tx, ny - this.ty) > 0.35 ? Math.hypot(nx - this.tx, ny - this.ty) : 0;
      this.tx = nx; this.ty = ny; this.next = t + 0.4;
    } else if (t > this.next) {                             // wandering fixations
      const nx = (this.r() - 0.5) * 0.6, ny = (this.r() - 0.5) * 0.27;
      jump = Math.hypot(nx - this.tx, ny - this.ty); this.tx = nx; this.ty = ny; this.next = t + 0.9 + this.r() * 2.6;
    }
    if (t > this.mnext) { this.mx = (this.r() - 0.5) * 0.07; this.my = (this.r() - 0.5) * 0.05; this.mnext = t + 0.25 + this.r() * 0.5; }   // micro-saccades
    this.ex = damp(this.ex, this.tx + this.mx, 0.035, dt); this.ey = damp(this.ey, this.ty + this.my, 0.035, dt);
    this.hx = damp(this.hx, this.tx, 0.32, dt); this.hy = damp(this.hy, this.ty, 0.32, dt);
    return { ex: this.ex, ey: this.ey, hx: this.hx, hy: this.hy, jump };
  }
}

// Mouth from a loudness envelope (+ optional spectral centroid 0..1 for round "oo" vs wide "ee"). Each rising edge is a syllable
// that pops the mouth open; a loud peak well above the recent average is reported as an emphasis `beat`.
export class Lipsync {
  constructor(rnd = Math.random) { this.r = rnd; this.env = 0; this.prev = 0; this.syl = 0; this.cool = 0; this.avg = 0; this.vis = 0; this.cool2 = 0; this.open = 0; this.width = 0; }
  update(dt, level, centroid = -1) {
    level = clamp(level, 0, 1); this.cool -= dt; this.cool2 -= dt;
    this.env = damp(this.env, level, level > this.env ? 0.02 : 0.06, dt);
    this.avg = damp(this.avg, level, 1.2, dt);
    let beat = false;
    if (level - this.prev > 0.07 && this.cool <= 0) { this.syl = 1; this.cool = 0.09; this.vis = centroid >= 0 ? (centroid - 0.5) * 2 : this.r() * 2 - 1; }
    if (level > 0.3 && level > this.avg * 1.7 && this.cool2 <= 0) { beat = true; this.cool2 = 0.5; }
    this.prev = level; this.syl = damp(this.syl, 0, 0.05, dt);
    const speaking = this.env > 0.02;
    const open = speaking ? clamp(this.env * 2.4 * (0.6 + 0.4 * this.syl), 0, 1) * (1 - 0.25 * Math.max(0, this.vis)) : 0;
    this.open = damp(this.open, open, 0.025, dt);
    this.width = damp(this.width, speaking ? clamp(this.vis * 0.7, -1, 1) : 0, 0.05, dt);
    return { open: this.open, width: this.width, beat };
  }
}

// Gestures timed to the words she says. Returns [{name, at (0..1 of the speech), power}] (at most 4, spaced out).
export function gestureForText(text) {
  const s = String(text || ''), n = Math.max(1, s.length), out = [];
  const add = (name, idx, power = 1) => out.push({ name, at: clamp(idx / n, 0.04, 0.96), power });
  let m;
  const neg = /\b(no|not|never|don't|dont|can't|cant|won't|wont|stop|nothing|enough)\b/gi;
  while ((m = neg.exec(s))) { add('shake_head', m.index, 0.7); break; }
  const yes = /\b(yes|yeah|sure|okay|ok|fine|alright|right|exactly|indeed)\b/gi;
  while ((m = yes.exec(s))) { add('nod', m.index, 0.8); break; }
  if (/\?\s*$/.test(s)) add('tilt', n * 0.8, 1);
  const ex = /!/g; while ((m = ex.exec(s))) { add('beat', m.index, 1.4); }
  const dot = /[.;](\s|$)/g; while ((m = dot.exec(s))) { if (m.index < n - 2) add('beat', m.index, 0.55); }
  if (/\.\.\./.test(s)) add('sigh', s.indexOf('...'), 1);
  out.sort((a, b) => a.at - b.at);
  const keep = []; for (const g of out) if (!keep.length || g.at - keep[keep.length - 1].at > 0.12) keep.push(g);
  return keep.slice(0, 4);
}
export const speechSeconds = (text) => clamp(String(text || '').trim().split(/\s+/).length / 2.7, 0.8, 14);

// Frame-rate watchdog: sustained low fps steps quality down (0 full, 1 hair at half rate, 2 also glow off); sustained high fps steps back up.
export class Perf {
  constructor() { this.fps = 60; this.level = 0; this.low = 0; this.high = 0; }
  update(dt) {
    dt = clamp(dt, 1e-3, 0.5); this.fps = damp(this.fps, 1 / dt, 0.5, dt);
    if (this.fps < 20) { this.low += dt; this.high = 0; }
    else if (this.fps > 38) { this.high += dt; this.low = 0; }
    else { this.low = Math.max(0, this.low - dt); this.high = Math.max(0, this.high - dt); }
    if (this.low > 2.5 && this.level < 2) { this.level++; this.low = 0; }
    if (this.high > 8 && this.level > 0) { this.level--; this.high = 0; }
    return this.level;
  }
}

// ---------------------------------------------------------------- spring chains (hair / cloth)
const KINDS = [
  [/Hair/, { gain: 0.055, w0: 11, wind: 1.0 }],
  [/Skirt|Cape|Cloak|Coat/, { gain: 0.05, w0: 8, wind: 0.7 }],
  [/Sleeve/, { gain: 0.03, w0: 9, wind: 0.4 }],
];
const DEFAULT_KIND = { gain: 0.025, w0: 9, wind: 0.3 };
export function chainInfo(name) {
  const m = /^\+(.*?)(\d+)$/.exec(name);
  const kind = (KINDS.find(([re]) => re.test(name)) || [null, DEFAULT_KIND])[1];
  return { base: m ? m[1] : name, level: m ? parseInt(m[2], 10) : 1, kind };
}
const softLimit = (v, lim) => (v >= 0 ? v : -lim * Math.tanh(-v / lim));   // one-sided: moving "into the body" saturates at -lim

// entries: [{name, side (+1/-1/0: which side of the body), zsign (+1 back, -1 front, 0 neither)}]
export class ChainSim {
  constructor(entries, lim = 0.012) {
    this.lim = lim; this.p = { x: 0, z: 0 }; this.v = { x: 0, z: 0 }; this.prev = { hipX: 0, headY: 0 };
    this.bones = entries.map((e) => { const c = chainInfo(e.name); return { name: e.name, side: e.side || 0, zsign: e.zsign || 0, level: c.level, kind: c.kind,
      ph: (e.name.length * 7.7) % 6.28 + c.level * 0.7, x: 0, z: 0, vx: 0, vz: 0, rx: 0, rz: 0 }; });
  }
  step(dt, s) {
    dt = clamp(dt, 1e-3, 0.1);
    const vx = clamp((s.hipX - this.prev.hipX) / dt, -0.3, 0.3), vy = clamp((s.headY - this.prev.headY) / dt, -2, 2);
    this.prev = { hipX: s.hipX, headY: s.headY };
    const tx = -vx * 2.0 - vy * 0.12, tz = 0.25 * Math.sin(s.t * 1.1) - s.chestP * 3, h = Math.min(dt, 1 / 60), n = Math.ceil(dt / h);
    for (let i = 0; i < n; i++) {                           // shared "body" stage: a soft spring that lags the motion
      this.v.x += ((tx - this.p.x) * 40 - this.v.x * 7) * h; this.p.x += this.v.x * h;
      this.v.z += ((tz - this.p.z) * 40 - this.v.z * 7) * h; this.p.z += this.v.z * h;
    }
    const gust = 0.5 * (Math.sin(s.t * 0.7) + Math.sin(s.t * 1.9 + 2)) * (0.5 + 0.5 * Math.sin(s.t * 0.13));
    const shake = s.shake ? 0.1 * Math.sin(s.t * 31) * s.shake : 0;
    const wx = clamp(this.p.x, -1, 1) * 0.5 + shake, wz = clamp(this.p.z, -1, 1) * 0.35;
    for (const b of this.bones) {                            // per-bone stage: stiffer near the root, looser (more lag) toward the tip
      const w = 0.1 * Math.sin(s.t * 1.7 + b.ph) + 0.12 * b.kind.wind * gust;
      const gx = b.kind.gain, w0 = b.kind.w0 / (1 + 0.2 * b.level), z = 2 * 0.55 * w0;
      const tgtX = (wz + w * 0.5) * gx, tgtZ = (-wx + w) * gx;
      for (let i = 0; i < n; i++) {
        b.vx += (w0 * w0 * (tgtX - b.x) - z * b.vx) * h; b.x += b.vx * h;
        b.vz += (w0 * w0 * (tgtZ - b.z) - z * b.vz) * h; b.z += b.vz * h;
      }
      b.rx = b.zsign ? b.zsign * softLimit(b.x * b.zsign, this.lim) : b.x;      // soft collision: hair/cloth may not swing into the body
      b.rz = b.side ? b.side * softLimit(b.z * b.side, this.lim) : b.z;
    }
    return this.bones;
  }
}
