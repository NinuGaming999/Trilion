import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

import pytest  # noqa: E402

from trilion.core import avatar as av  # noqa: E402
from trilion.core.hud import WebHud  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class FakeLLM:
    def __init__(self, reply='{"say": "Hm.", "emotion": "annoyed", "gesture": "glare"}'):
        self.reply, self.calls = reply, []

    def chat_stream(self, messages, **kw):
        self.calls.append(messages)
        yield self.reply


class FakeAssistant:
    busy = False

    def __init__(self):
        self.said, self.submitted = [], []

    def say_direct(self, t):
        self.said.append(t)

    def submit_text(self, t):
        self.submitted.append(t)


@pytest.fixture
def server(tmp_path):
    model = tmp_path / "model"
    (model / "source").mkdir(parents=True)
    (model / "source" / "arlecchino.fbx").write_bytes(b"FBX")
    (model / "source" / "notes.exe").write_bytes(b"x")
    hud = WebHud(0)
    asst = FakeAssistant()
    svc = av.AvatarService({}, hud, model_dir=model, llm=FakeLLM(), assistant=asst)
    hud.start()
    yield hud, svc, asst, tmp_path
    hud.stop()


def req(hud, path, method="GET", body=None, host=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(hud.url.rstrip("/") + path, data=data, method=method)
    r.add_header("Host", host or f"127.0.0.1:{hud.port}")
    if token:
        r.add_header("X-Trilion-Token", token)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_page_served_with_token_and_config(server):
    hud, svc, _, _ = server
    code, body = req(hud, "/avatar")
    html = body.decode()
    assert code == 200 and hud.token in html and "__TOKEN__" not in html and "__CONFIG__" not in html
    assert "/avatar/model/source/arlecchino.fbx" in html


def test_host_header_blocked(server):
    hud, *_ = server
    assert req(hud, "/avatar", host="evil.example.com")[0] == 403
    assert req(hud, "/avatar", host="evil.example.com:%d" % hud.port)[0] == 403
    assert req(hud, "/avatar", host=f"localhost:{hud.port}")[0] == 200


def test_post_requires_token(server):
    hud, svc, asst, _ = server
    assert req(hud, "/avatar/say", "POST", {"text": "hi"})[0] == 403
    assert req(hud, "/avatar/say", "POST", {"text": "hi"}, token="wrong")[0] == 403
    assert req(hud, "/avatar/say", "POST", {"text": "hi"}, token=hud.token)[0] == 200
    assert asst.submitted == ["hi"]


def test_post_size_and_json_limits(server):
    hud, *_ = server
    assert req(hud, "/avatar/say", "POST", {"text": "x" * 9000}, token=hud.token)[0] == 413
    r = urllib.request.Request(hud.url + "avatar/say", data=b"{nope", method="POST")
    r.add_header("X-Trilion-Token", hud.token)
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(r)
    assert e.value.code == 400


def test_say_text_is_clipped(server):
    hud, svc, asst, _ = server
    req(hud, "/avatar/say", "POST", {"text": "a" * 1000}, token=hud.token)
    assert len(asst.submitted[0]) == 300


@pytest.mark.parametrize("p", ["/avatar/static/../hud.py", "/avatar/static/..%2fhud.py", "/avatar/static/%2e%2e/hud.py",
                               "/avatar/model/../../x", "/avatar/static//etc/passwd", "/avatar/static/C:/Windows/win.ini",
                               "/avatar/static/..\\hud.py"])
def test_path_traversal_blocked(server, p):
    assert req(server[0], p)[0] in (400, 403, 404)


def test_static_and_model_extension_allowlist(server):
    hud, *_ = server
    assert req(hud, "/avatar/static/mind.js")[0] == 200
    assert req(hud, "/avatar/static/rig.py")[0] == 404
    code, body = req(hud, "/avatar/model/source/arlecchino.fbx")
    assert code == 200 and body == b"FBX"
    assert req(hud, "/avatar/model/source/notes.exe")[0] == 404
    assert req(hud, "/avatar/audio/..%2f..%2fx.wav")[0] == 404
    assert req(hud, "/avatar/audio/nothing.wav")[0] == 404


def test_disabled_service_serves_nothing(server):
    hud, svc, *_ = server
    svc.enabled = False
    assert req(hud, "/avatar")[0] == 404


def test_safe_join_rules(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert av.safe_join(tmp_path, "a.txt")
    for bad in ("../a.txt", "..", "", "/", "a/../../x", "c:/x", "a\x00.txt", "..\\a.txt", "missing.txt"):
        assert av.safe_join(tmp_path, bad) is None


def test_zip_slip_rejected(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../escaped.txt", "pwn")
    dest = tmp_path / "out"
    with pytest.raises(RuntimeError):
        av.safe_extract(z, dest)
    assert not (tmp_path / "escaped.txt").exists()


def test_model_extract_and_missing_fbx(tmp_path, monkeypatch):
    hud = WebHud(0)
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as f:
        f.writestr("source/arlecchino.fbx", "FBX")
        f.writestr("textures/a.png", "png")
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as f:
        f.writestr("readme.txt", "no model")
    monkeypatch.setattr(av, "__file__", str(tmp_path / "x" / "y" / "z.py"))   # no repo copy -> download path
    for z, ok in ((good, True), (bad, False)):
        monkeypatch.setattr(av, "download", lambda url, dest, prog=None, z=z: z)
        svc = av.AvatarService({}, hud, model_dir=tmp_path / ("m_" + z.stem))
        assert svc.ensure_model() is ok
        assert (svc.status["error"] is None) is ok
        assert svc.status["downloading"] is False


# ---------------------------------------------------------------- AvatarMind
def make_mind(llm=None, asst=None, clock=None, cfg=None):
    t = [1000.0]
    m = av.AvatarMind(cfg if cfg is not None else {}, llm or FakeLLM(), asst or FakeAssistant(), clock or (lambda: t[0]))
    return m, t


def wait(m):
    for _ in range(200):
        if not m.busy:
            return
        time.sleep(0.01)
    raise AssertionError("mind stayed busy")


def test_parse_variants():
    p = av.AvatarMind.parse
    assert p('{"say": "Hands to yourself.", "emotion": "angry", "gesture": "glare"}') == ("Hands to yourself.", "angry", "glare")
    assert p('sure: {"say": "x", "emotion": "bogus", "gesture": "dance"} done') == ("x", "neutral", "none")
    assert p('"Just text"') == ("Just text", "neutral", "none")
    assert p("") == ("", "neutral", "none")
    assert len(p(json.dumps({"say": "a " * 200}))[0]) <= 140
    assert p("  many   spaces\nhere ")[0] == "many spaces here"


def test_build_messages_has_persona_facts_and_history():
    m, _ = make_mind()
    m.recent = ["one", "two", "three", "four"]
    msgs = m.build_messages({"type": "touch", "level": "angry", "anger": 0.6, "secret": "no", "zone": "head"})
    assert msgs[0]["role"] == "system" and msgs[0]["content"] == av.PERSONA
    facts = json.loads(msgs[1]["content"])
    assert facts["level"] == "angry" and facts["zone"] == "head" and "secret" not in facts
    assert facts["earlier_lines"] == ["two", "three", "four"]


def test_reaction_publishes_line_and_speaks():
    asst = FakeAssistant()
    m, _ = make_mind(asst=asst)
    assert m.handle({"type": "touch", "level": "annoyed"}) is True
    wait(m)
    assert m.line["text"] == "Hm." and m.line["emotion"] == "annoyed" and m.line["gesture"] == "glare" and m.line["id"] == 1
    assert asst.said == ["Hm."]


def test_speaking_can_be_turned_off():
    asst = FakeAssistant()
    m, _ = make_mind(asst=asst, cfg={"avatar_speak": False})
    m.handle({"type": "touch"})
    wait(m)
    assert m.line and asst.said == []


def test_rate_limit_busy_unknown_and_real_task():
    asst = FakeAssistant()
    m, t = make_mind(asst=asst)
    assert m.handle({"type": "nonsense"}) is False
    assert m.handle({"type": "touch"}) is True
    wait(m)
    assert m.handle({"type": "touch"}) is False          # inside the 4 s gap
    t[0] += 5
    asst.busy = True
    assert m.handle({"type": "touch"}) is False          # never talk over a real task
    asst.busy = False
    assert m.handle({"type": "touch"}) is True
    wait(m)
    assert m.handle({"type": "idle"}) is True            # separate kinds have separate gaps
    wait(m)
    m.busy = True
    t[0] += 1000
    assert m.handle({"type": "hello"}) is False          # one reaction at a time


def test_llm_failure_is_swallowed_and_frees_mind():
    class Boom(FakeLLM):
        def chat_stream(self, *a, **k):
            raise RuntimeError("model down")
    m, _ = make_mind(llm=Boom())
    assert m.handle({"type": "touch"}) is True
    wait(m)
    assert m.line is None and m.busy is False


def test_state_hook_exposes_line(server):
    hud, svc, *_ = server
    svc.mind.handle({"type": "touch"})
    wait(svc.mind)
    data = json.loads(req(hud, "/state")[1])
    assert data["avatar"]["line"]["text"] == "Hm."


def test_event_route_reaches_mind(server):
    hud, svc, *_ = server
    code, body = req(hud, "/avatar/event", "POST", {"type": "touch", "level": "angry"}, token=hud.token)
    assert code == 200 and json.loads(body)["ok"] is True
    wait(svc.mind)
    assert svc.mind.line is not None


# ---------------------------------------------------------------- filler lines <-> mind.js
def test_filler_lines_match_mind_js():
    src = (ROOT / "trilion" / "web" / "avatar" / "mind.js").read_text(encoding="utf-8")
    block = re.search(r"CANNED\s*=\s*\{(.*?)\};", src, re.S).group(1)
    js_lines = [a or b for a, b in re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", block)]
    assert js_lines == av.FILLER_LINES


def test_filler_slugs_unique_and_wav_safe():
    slugs = [av.slug(t) for t in av.FILLER_LINES]
    assert len(set(slugs)) == len(slugs) and all(re.fullmatch(r"[a-z\-]+", s) for s in slugs)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_mind_js_behaviour_with_node():
    code = """
import { Mind, CANNED } from './trilion/web/avatar/mind.js';
const m = new Mind(() => 0);
let t = 0, last;
for (let i = 0; i < 12; i++) { t += 0.4; last = m.touch('head', 'poke', t); }
const levels = ['calm','annoyed','angry','furious'];
if (!last || !levels.includes(last.level)) throw new Error('bad touch result ' + JSON.stringify(last));
if (last.anger <= 0) throw new Error('anger should build');
if (!Object.values(CANNED).flat().includes(last.canned)) throw new Error('canned line not from CANNED');
for (let i = 0; i < 400; i++) { t += 0.5; m.update(0.5, t); }
if (m.level() !== 'calm') throw new Error('should cool down to calm, got ' + m.level());
console.log('ok');
"""
    r = subprocess.run(["node", "--input-type=module", "-e", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_look_module_parses_and_is_wired_after_face():
    d = ROOT / "trilion" / "web" / "avatar"
    r = subprocess.run(["node", "--check", str(d / "look.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    src = (d / "avatar.js").read_text(encoding="utf-8")
    assert "makeLook" in src and src.index("new Face(") < src.index("look.apply(root)")   # chains onto face.js's shader patch
    assert "#include <opaque_fragment>" in (d / "look.js").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_unify_skeletons_hair_follows_head_node():
    """Two skeleton copies; in one, the head bone hangs under duplicate non-skeleton parents (like the FBX hair/body copies)."""
    code = """
import * as T from './trilion/web/avatar/lib/three.module.min.js';
import { unifySkeletons } from './trilion/web/avatar/skel.js';
const root = new T.Group();
function bone(n, y) { const b = new T.Bone(); b.name = n; b.position.set(0, y, 0); return b; }
function copy(dups) {                       // Neck -> [dup Neck, dup Head ...] -> Head
  const neck = bone('Neck', 1); let tip = neck;
  for (let i = 0; i < dups; i++) { const d = bone(i ? 'Head' : 'Neck', 0.1); tip.add(d); tip = d; }
  const head = bone('Head', 0.5); tip.add(head); root.add(neck);
  return { neck, head, bones: [neck, head] };
}
function mesh(c, name) {
  const g = new T.BufferGeometry(); g.setAttribute('position', new T.Float32BufferAttribute([0, 1.5, 0, 0.1, 1.5, 0, 0, 1.6, 0.1], 3));
  g.setAttribute('skinIndex', new T.Uint16BufferAttribute([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0], 4));
  g.setAttribute('skinWeight', new T.Float32BufferAttribute([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0], 4));
  const m = new T.SkinnedMesh(g, new T.MeshBasicMaterial({ name })); m.material.name = name; root.add(m);
  root.updateMatrixWorld(true);
  m.bind(new T.Skeleton(c.bones), m.matrixWorld); return m;
}
const clean = copy(0), dirty = copy(2);
// make rest poses agree (dirty copy's duplicate parents sit at the same place as the clean chain)
dirty.neck.children[0].position.set(0, 0, 0); dirty.neck.children[0].children[0].position.set(0, 0, 0);
const mFace = mesh(clean, 'face'), mHair = mesh(dirty, 'hair');
const info = unifySkeletons(T, root);
if (info.unified !== 1 || info.skipped.length) throw new Error('not unified ' + JSON.stringify(info));
if (mHair.skeleton.bones[1] !== mFace.skeleton.bones[1] || mHair.skeleton.bones[0] !== mFace.skeleton.bones[0]) throw new Error('bones not shared');
// rotate the neck and the head: both meshes now see exactly the same head transform
mFace.skeleton.bones[0].rotation.y = 0.7; mFace.skeleton.bones[1].rotation.x = 0.4; root.updateMatrixWorld(true);
const a = new T.Vector3(), b = new T.Vector3(); mFace.skeleton.update(); mHair.skeleton.update();
mFace.getVertexPosition(0, a); mHair.getVertexPosition(0, b);
if (a.distanceTo(b) > 1e-6) throw new Error('hair and face disagree by ' + a.distanceTo(b));
// a copy whose bind pose differs must be left alone
const odd = copy(0); odd.neck.position.set(0.3, 1, 0); const mOdd = mesh(odd, 'dress');
const info2 = unifySkeletons(T, root);
if (!info2.skipped.some((s) => s.startsWith('dress'))) throw new Error('mismatched bind pose was not skipped');
console.log('ok');
"""
    r = subprocess.run(["node", "--input-type=module", "-e", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-800:]


def test_every_js_import_resolves_to_a_bundled_file():
    """A missing vendored file would blank the whole avatar page, so walk the import graph from index.html's modules."""
    web = ROOT / "trilion" / "web" / "avatar"
    lib = web / "lib"
    seen, todo, missing = set(), [web / "avatar.js"], []
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        src = f.read_text(encoding="utf-8")
        for spec in re.findall(r"""(?:import|export)\s[^'";]*?from\s*['"]([^'"]+)['"]|import\s*['"]([^'"]+)['"]""", src, re.S):
            spec = spec[0] or spec[1]
            if spec == "three":
                target = lib / "three.module.min.js"
            elif spec.startswith("three/addons/"):
                target = lib / "jsm" / spec[len("three/addons/"):]
            elif spec.startswith("."):
                target = (f.parent / spec).resolve()
            else:
                missing.append((f.name, spec))
                continue
            if not target.is_file():
                missing.append((f.name, spec))
            elif target.suffix == ".js" and "three.module" not in target.name:
                todo.append(target)
    assert not missing, missing
    assert any(p.name == "UnrealBloomPass.js" for p in seen) and any(p.name == "skel.js" for p in seen)


def test_postprocessing_files_are_served(server):
    hud, *_ = server
    for rel in ("postprocessing/UnrealBloomPass.js", "postprocessing/EffectComposer.js", "shaders/LuminosityHighPassShader.js"):
        assert req(hud, "/avatar/static/lib/jsm/" + rel)[0] == 200


def test_halo_and_glow_never_write_opaque_alpha():
    look = (ROOT / "trilion" / "web" / "avatar" / "look.js").read_text(encoding="utf-8")
    assert "CustomBlending" in look and "AdditiveBlending" not in look.split("makeHalo")[1]
    av_js = (ROOT / "trilion" / "web" / "avatar" / "avatar.js").read_text(encoding="utf-8")
    assert "blendSrcAlpha = THREE.ZeroFactor" in av_js and "max(c.a, max(c.r" in av_js
