// Mind: her mood. Pure logic (no rendering), so it can be unit-tested. Touches build ANGER; time cools it down.
// calm < 0.22 <= annoyed < 0.52 <= angry < 0.82 <= furious. Reaching furious makes her SULK (ignore you) for a while.
export const LEVELS = ['calm', 'annoyed', 'angry', 'furious'];
export const ZONE_W = { face: 1.3, head: 1.0, hair: 0.7, neck: 1.2, chest: 1.8, belly: 1.4, arm: 0.8, hand: 0.9, leg: 1.1, back: 1.2, other: 1.0 };
export const CANNED = {
  calm: ['...?', 'Hm.', 'Yes?'],
  annoyed: ['Hands to yourself.', "Don't.", 'Hm. Careful.'],
  angry: ['That is enough.', 'You test my patience.', 'Once more, and I leave.'],
  furious: ['Enough!', 'Insolent.', 'Do not touch me again.'],
  cooled: ['...Better.', 'Hm. Good.', 'Now, where were we.'],
};
const TH = [0.22, 0.52, 0.82];

export class Mind {
  constructor(rng = Math.random) {
    this.rng = rng; this.anger = 0; this.touches = []; this.lastTouch = -99; this.sulkUntil = 0;
    this.sinceAI = 0; this.lastAI = -99; this.lastLine = ''; this.peak = 0;
  }
  static levelOf(a) { return a >= TH[2] ? 'furious' : a >= TH[1] ? 'angry' : a >= TH[0] ? 'annoyed' : 'calm'; }
  level() { return Mind.levelOf(this.anger); }
  sulking(t) { return t < this.sulkUntil; }
  pick(list) {
    let s = list[Math.floor(this.rng() * list.length) % list.length];
    if (s === this.lastLine && list.length > 1) s = list[(list.indexOf(s) + 1) % list.length];
    this.lastLine = s; return s;
  }
  // kind: poke | hold | stroke.  Returns what the page should do right now (instantly, no AI needed).
  touch(zone, kind, t, strength = 1) {
    this.touches = this.touches.filter((x) => t - x < 6);
    const recent = this.touches.length;
    const base = kind === 'hold' ? 0.045 : kind === 'stroke' ? 0.06 : 0.095;
    const inc = base * (ZONE_W[zone] || 1) * (1 + 0.18 * Math.min(recent, 5)) * (this.sulking(t) ? 1.4 : 1) * strength;
    const prev = this.level();
    this.anger = Math.min(1, this.anger + inc);
    this.touches.push(t); this.lastTouch = t; this.sinceAI++;
    const lv = this.level();
    const escalated = LEVELS.indexOf(lv) > LEVELS.indexOf(prev);
    let snap = false;
    if (lv === 'furious' && !this.sulking(t) && escalated) { this.sulkUntil = t + 14; snap = true; }
    this.peak = Math.max(this.peak, this.anger);
    const needAI = escalated || (this.sinceAI >= 3 && t - this.lastAI > 5);
    if (needAI) { this.sinceAI = 0; this.lastAI = t; }
    const side = this.rng() < 0.5 ? -1 : 1;
    const clips = [];
    if (zone === 'arm' || zone === 'hand') clips.push({ clip: 'pullArm', side, power: 1 });
    else if (zone === 'chest' || zone === 'belly' || zone === 'back' || lv === 'angry' || lv === 'furious') clips.push({ clip: 'recoil', side, power: lv === 'calm' ? 0.6 : 1 });
    else clips.push({ clip: 'flinch', side, power: lv === 'calm' ? 0.7 : 1 });
    if (lv !== 'calm') clips.push({ clip: 'glare', dur: lv === 'annoyed' ? 1.4 : 2.2 });
    if (lv === 'angry') clips.push({ clip: 'threat', dur: 1.6 });
    if (snap) clips.push({ clip: 'snap', side, dur: 2.6 });
    return { anger: this.anger, level: lv, escalated, snap, clips, canned: this.pick(CANNED[lv]), needAI, zone, kind };
  }
  update(dt, t) {
    const prev = this.level();
    if (t - this.lastTouch > 2.5) this.anger = Math.max(0, this.anger - (this.sulking(t) ? 0.025 : 0.05) * dt);
    const lv = this.level();
    const cooled = prev !== 'calm' && lv === 'calm' && this.peak >= TH[0];
    if (cooled) this.peak = 0;
    return { cooled, level: lv, sulking: this.sulking(t) };
  }
}
