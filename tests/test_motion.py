import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "trilion" / "web" / "avatar"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def run_js(body, imports="import * as M from './trilion/web/avatar/motion.js';"):
    code = imports + "\nconst eq=(c,m)=>{ if(!c) throw new Error(m); };\n" + body + "\nconsole.log('ok');"
    r = subprocess.run(["node", "--input-type=module", "-e", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-1200:]


@needs_node
def test_breath_is_asymmetric_and_bounded():
    run_js("""
eq(M.breathCurve(0) === 0 && Math.abs(M.breathCurve(0.38) - 1) < 1e-9, 'peak at 38%');
eq(M.breathCurve(0.95) === 0, 'pause at the bottom');
eq(M.breathCurve(0.2) > 0.3 && M.breathCurve(0.2) < 0.7, 'inhale mid-way');
eq(1 - M.breathCurve(0.63) > 0.3, 'exhale is slower than inhale: 25% after the peak it is still mostly full');
let r = 0.4; const rnd = () => (r = (r * 9301 + 49297) % 233280 / 233280); const b = new M.Breath(rnd); let lo = 9, hi = -9;
for (let i = 0; i < 4000; i++) { const v = b.update(0.016, i > 2000 ? 1 : 0); lo = Math.min(lo, v); hi = Math.max(hi, v); }
eq(lo >= -0.7 && hi <= 1.0 && hi - lo > 0.9, 'range ' + lo + ' ' + hi);
""")


@needs_node
def test_clip_envelope():
    run_js("""
eq(M.envS(-1, 1) === 0 && M.envS(1, 1) === 0 && M.envS(2, 1) === 0, 'zero outside');
eq(M.envS(0.05, 1, 0.1, 0.5) < 0.9 && M.envS(0.5, 1, 0.1, 0.5) === 1, 'ramps up then holds');
eq(M.envS(0.95, 1, 0.1, 0.5) < 0.2, 'fades out');
eq(M.envS(0.1, 0.1, 5, 5) === 0, 'oversized a/r are clamped, no NaN');
for (let t = 0; t < 1; t += 0.01) eq(Number.isFinite(M.envS(t, 1, 0, 0)), 'zero a/r is safe');
""")


@needs_node
def test_eyes_lead_the_head_and_report_jumps():
    run_js("""
const g = new M.Gaze(() => 0.5); let j = 0, last;
for (let i = 0; i < 6; i++) { last = g.update(0.016, i * 0.016, { x: 0.8, y: 0.2, w: 1 }); j = Math.max(j, last.jump); }
eq(j > 0.7, 'a big fixation change is reported as a jump (used to trigger a blink)');
eq(Math.abs(last.ex) > Math.abs(last.hx) * 2.5, 'eyes are ahead of the head: ' + last.ex + ' vs ' + last.hx);
for (let i = 0; i < 200; i++) last = g.update(0.016, 1 + i * 0.016, { x: 0.8, y: 0.2, w: 1 });
eq(Math.abs(last.hx - 0.8) < 0.05, 'the head catches up');
const w = new M.Gaze(); let moved = 0; for (let i = 0; i < 900; i++) { const o = w.update(0.016, i * 0.016, { w: 0 }); moved = Math.max(moved, Math.abs(o.ex)); }
eq(moved > 0.05 && moved < 0.5, 'wandering stays in range: ' + moved);
""")


@needs_node
def test_lipsync_syllables_beats_and_visemes():
    run_js("""
const l = new M.Lipsync(() => 0.5); let o;
for (let i = 0; i < 60; i++) o = l.update(0.016, 0, -1);
eq(o.open < 0.01 && !o.beat, 'silent mouth is closed');
let opens = [], beats = 0;
for (let i = 0; i < 200; i++) { const lvl = (i % 24 < 12) ? 0.5 + 0.2 * Math.sin(i) : 0.08; o = l.update(0.016, lvl, -1); opens.push(o.open); if (o.beat) beats++; }
eq(Math.max(...opens) > 0.4 && Math.min(...opens.slice(20)) < Math.max(...opens) * 0.7, 'mouth opens and closes with syllables');
const hi = new M.Lipsync(), lo = new M.Lipsync(); let a, b;
for (let i = 0; i < 120; i++) { a = hi.update(0.016, 0.1 + (i % 10 === 0 ? 0.5 : 0.3), 0.95); b = lo.update(0.016, 0.1 + (i % 10 === 0 ? 0.5 : 0.3), 0.05); }
eq(a.width > 0.2 && b.width < -0.2, 'bright sound = wide "ee", dark sound = round "oo": ' + a.width + ' ' + b.width);
const e = new M.Lipsync(); let got = false; for (let i = 0; i < 400; i++) { const o2 = e.update(0.016, i === 300 ? 0.95 : 0.25, -1); if (o2.beat && i >= 300) got = true; }
eq(got, 'a loud peak above the recent average is an emphasis beat');
""")


@needs_node
def test_gestures_follow_the_words():
    run_js("""
const names = (t) => M.gestureForText(t).map((g) => g.name);
eq(names("No. I won't.").includes('shake_head'), 'negation shakes the head');
eq(names('Sure, fine.').includes('nod'), 'agreement nods');
eq(names('Why would I?').includes('tilt'), 'a question tilts the head');
eq(names('Stop that!').includes('beat'), 'an exclamation gets a beat');
eq(names('Hmm... fine.').includes('sigh'), 'an ellipsis sighs');
eq(M.gestureForText('').length === 0 && M.gestureForText(null).length === 0, 'empty text, no gestures');
const long = M.gestureForText('No! Yes! Stop! Fine! Sure! Never! Okay! Right!'); eq(long.length <= 4, 'at most 4 gestures');
for (let i = 1; i < long.length; i++) eq(long[i].at - long[i - 1].at > 0.1 && long[i].at >= long[i - 1].at, 'spaced and ordered');
eq(M.speechSeconds('a b c d e f g h i j') > 3 && M.speechSeconds('') >= 0.8, 'speech time estimate');
""")


@needs_node
def test_perf_watchdog_steps_down_and_up():
    run_js("""
const p = new M.Perf(); for (let i = 0; i < 400; i++) p.update(1 / 60); eq(p.level === 0, 'healthy at 60 fps');
for (let i = 0; i < 400; i++) p.update(1 / 10); eq(p.level === 2, 'drops to quality 2 at 10 fps: ' + p.level);
for (let i = 0; i < 400; i++) p.update(1 / 10); eq(p.level === 2, 'never below 2');
for (let i = 0; i < 2000; i++) p.update(1 / 60); eq(p.level === 0, 'recovers when fast again: ' + p.level);
const q = new M.Perf(); for (let i = 0; i < 600; i++) q.update(1 / 28); eq(q.level === 0, 'a mid frame rate does not flap');
""")


@needs_node
def test_chain_springs_are_stable_lag_and_do_not_enter_the_body():
    run_js("""
const mk = (n, side, zs) => ({ name: n, side, zsign: zs });
const sim = new M.ChainSim([mk('+HairS_R_A01', 1, 0), mk('+HairS_R_A05', 1, 0), mk('+HairS_L_A01', -1, 0), mk('+HairB_CB_A01', 0, 1), mk('+HairF_C_A01', 0, -1), mk('+SkirtB_C_A01', 0, 1)]);
let mx = 0, inward = 0;
for (let i = 0; i < 6000; i++) {
  const t = i * 0.016, bones = sim.step(0.016, { hipX: 0.03 * Math.sin(t * 5), headY: 1.5 * Math.sin(t * 3.1), chestP: 0.1 * Math.sin(t * 2), t, shake: i > 3000 ? 1 : 0 });
  for (const b of bones) { eq(Number.isFinite(b.rx) && Number.isFinite(b.rz), 'finite'); mx = Math.max(mx, Math.abs(b.rx), Math.abs(b.rz));
    if (b.side) inward = Math.min(inward, b.rz * b.side); if (b.zsign) inward = Math.min(inward, b.rx * b.zsign); }
}
eq(mx < 0.08, 'bounded: ' + mx);
eq(inward >= -0.0121, 'soft collision: nothing swings more than ~0.012 rad into the body, got ' + inward);
// lag: after a sudden push the long chain's tip peaks later than its root
const a = new M.ChainSim([mk('+HairX_A01', 0, 0), mk('+HairX_A05', 0, 0)]); const pk = [0, 0], at = [0, 0];
for (let i = 0; i < 150; i++) { const b = a.step(0.016, { hipX: i < 3 ? 0 : 0.05, headY: 0, chestP: 0, t: 0, shake: 0 }); b.forEach((x, k) => { if (Math.abs(x.rz) > pk[k]) { pk[k] = Math.abs(x.rz); at[k] = i; } }); }
eq(pk[0] > 0.002 && at[1] > at[0] + 10, 'the tip peaks well after the root: ' + at[0] + ' vs ' + at[1]);
eq(M.chainInfo('+HairX_A05').level === 5 && M.chainInfo('+HairX_A05').base === 'HairX_A', 'chain name parsing');
eq(M.chainInfo('+SleeveL_A01').kind.gain < M.chainInfo('+HairB_A01').kind.gain, 'hair swings more than sleeves');
""")


@needs_node
def test_animator_clip_blending_and_zones_with_a_stub_rig():
    run_js("""
const A = { rig: { bones: {}, rot() {}, move() {}, moveWorld() {} }, fp: { lidL: {}, lidR: {}, mouth: {}, gaze: {} } };
const an = new X.Animator(A); const ctx = { state: 'idle', out: 0, mic: 0, localOut: 0, anger: 0, level: 'calm', sulking: false, cam: { yaw: 0 }, pointer: { x: 0, y: 0, age: 99 } };
const run = (s) => { for (let i = 0; i < Math.round(s / 0.016); i++) an.update(0.016, ctx); };
// crossfade: a second nod releases the first one instead of stacking on top of it
an.play('nod'); run(0.2); an.play('nod', { power: 1 }); eq(an.clips.length === 2, 'both exist briefly'); run(0.4); eq(an.clips.length <= 1, 'the older one has faded out: ' + an.clips.length);
// different groups coexist
an.clips = []; an.play('nod'); an.play('flinch', { zone: 'head' }); eq(an.clips.length === 2, 'different groups overlap');
// fast attack, slow release for a flinch: strong within 0.12 s, still present at 0.6 s, gone by 1.2 s
const peak = (zone) => { an.clips = []; an.ch = {}; an.play('flinch', { zone, side: 1 }); let m = 0; for (let i = 0; i < 40; i++) { an.update(0.016, ctx); m = Math.max(m, Math.abs(an.ch.headP)); } return m; };
eq(peak('head') > peak('chest') * 1.15, 'a hit on the head tips it back further than one on the chest');
an.clips = []; an.ch = {}; an.play('flinch', { zone: 'arm', side: 1 }); run(0.3); eq(Math.abs(an.ch.chestY) > 0.002, 'a touch on the arm turns her toward it');
an.clips = []; an.play('flinch'); run(1.4); eq(an.clips.length === 0, 'clips end');
// every gesture the AI may pick is playable and has timing data
for (const g of X.GESTURES) if (g !== 'none') { eq(X.CLIPS[g], 'CLIPS entry for ' + g); an.play(g); run(0.2); }
eq(Object.keys(X.ARM_POSES).includes('crossed') && Object.keys(X.ARM_POSES).includes('chin'), 'signature poses exist');
// intensity scales motion; zero-ish intensity is nearly still
const rots = []; A.rig.rot = (n, x, y, z) => { if (n === 'ValveBipedBip01_Head1') rots.push(Math.abs(x) + Math.abs(y) + Math.abs(z)); };
an.clips = []; an.play('turn_away', { side: 1 }); an.intensity = 1; run(1); const full = Math.max(...rots); rots.length = 0;
an.clips = []; an.ch = {}; an.play('turn_away', { side: 1 }); an.intensity = 0.3; run(1); const low = Math.max(...rots);
eq(low < full * 0.6, 'intensity 0.3 moves much less: ' + low + ' vs ' + full);
""", imports="import * as M from './trilion/web/avatar/motion.js';\nimport * as X from './trilion/web/avatar/anim.js';")


def test_gesture_lists_match_between_page_and_backend():
    from trilion.core import avatar as av
    js = (WEB / "anim.js").read_text(encoding="utf-8")
    js_list = re.findall(r"'([a-z_]+)'", re.search(r"export const GESTURES = \[(.*?)\];", js, re.S).group(1))
    assert js_list == av.GESTURES
    for g in av.GESTURES:
        if g != "none":
            assert f"'{g}'" in js and (f"case '{g}'" in js), g          # every gesture has a clip implementation
    assert all(g in av.PERSONA for g in ("cross_arms", "chin", "dismiss"))   # the AI is told about the new ones
    assert av.AvatarMind.parse('{"say": "Hm.", "emotion": "calm", "gesture": "cross_arms"}')[2] == "cross_arms"


def test_motion_setting_plumbing():
    from trilion.core import avatar as av
    from trilion import paths
    assert av.motion_level({}) == 1.0 and av.motion_level({"avatar_motion": 0.6}) == 0.6
    assert av.motion_level({"avatar_motion": 99}) == 1.6 and av.motion_level({"avatar_motion": -3}) == 0.3 and av.motion_level({"avatar_motion": "x"}) == 1.0
    assert paths.DEFAULTS["avatar_motion"] == 1.0


def test_state_and_page_carry_the_motion_level(tmp_path):
    from trilion.core.hud import WebHud
    from trilion.core import avatar as av
    hud = WebHud(0)
    svc = av.AvatarService({"avatar_motion": 1.4}, hud, model_dir=tmp_path)
    assert svc.state_extra()["avatar"]["motion"] == 1.4
    assert '"motion": 1.4' in svc.page()


def test_motion_modules_are_wired_and_debug_panel_exists():
    src = (WEB / "avatar.js").read_text(encoding="utf-8")
    for token in ("gestureForText", "new Perf", "buildDebug", "ctx.typing", "A.timeScale", "PERF_ON", "ctx.spec"):
        assert token in src, token
    dbg = (WEB / "debug.js").read_text(encoding="utf-8")
    assert "CLIPS" in dbg and "intensity" in dbg and "A.timeScale" in dbg and "ARM_POSES" in dbg
