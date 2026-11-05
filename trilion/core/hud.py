"""HUD data shared by the on-screen overlay and the OBS Browser Source page.

* hud_lines(): the terminal-style lines (same text in both places).
* WebHud: a tiny HTTP server on 127.0.0.1 (this PC only) serving a transparent page with the animated core."""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("trilion.hud")


def bar(v, n=8):
    k = int(round(max(0.0, min(1.0, float(v or 0))) * n))
    return "\u2588" * k + "\u2591" * (n - k)


def _clip(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "\u2026"


def hud_lines(s, size="standard"):
    """-> list of (text, kind). kind: head | text | dim | ok | fail | run | you | reply | warn"""
    state = str(s.get("state", "idle")).upper()
    tps = f"{s['tps']:.1f} tok/s" if s.get("tps") else "-- tok/s"
    lines = [(f"TRILION v{s.get('version', '')}  [{state}]", "head"),
             (f"brain {_clip(s.get('brain', ''), 18)}  {tps}", "text")]
    if size == "compact":
        return lines
    vram = (f"vram {s['vram'] / 1024:.1f}/{s['vram_total'] / 1024:.0f}G"
            if s.get("vram") is not None and s.get("vram_total") else "gpu n/a")
    lines.append((f"cpu {s.get('cpu', 0):.0f}%  ram {s.get('ram', 0):.0f}%  {vram}", "dim"))
    lines.append((f"mic {bar(s.get('mic'))}  out {bar(s.get('out'))}", "dim"))
    g = s.get("game")
    if g and g.get("on"):
        held = ",".join(g.get("keys", []) + [b[0].upper() for b in g.get("buttons", [])]) or "-"
        mv = g.get("move") or (0, 0)
        lines.append((f"game {_clip(g.get('profile') or 'on', 9)} hold {_clip(held, 13)} mv {mv[0]:+d},{mv[1]:+d}", "run"))
    n = 5 if size == "full" else 3
    ev = s.get("events", [])[-n:]
    if not ev:
        lines.append(("> waiting for input...", "dim"))
    for e in ev:
        mark = {"ok": "\u2713", "fail": "\u2717", "run": "\u25b8", "you": ">", "reply": "<", "warn": "!"}.get(e["k"], ">")
        lines.append((f"{mark} {_clip(e['text'], 38)}", e["k"]))
    return lines


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Trilion HUD</title>
<style>
html,body{margin:0;background:transparent;overflow:hidden;font-family:Consolas,'Cascadia Mono',monospace}
#box{position:absolute;left:0;top:0;width:__W__px;padding:8px 10px 10px;box-sizing:border-box;
 background:__BG__;border:1px solid rgba(25,211,255,.55);border-radius:14px}
canvas{display:block;margin:0 auto}
#t{margin-top:4px;font-size:13px;line-height:17px;white-space:pre}
.head{color:#19d3ff;font-weight:bold}.text{color:#dff0ff}.dim{color:#7a9cc8}.ok{color:#34ffaa}.fail,.warn{color:#ff5f6e}
.run{color:#ffbf40}.you{color:#7fe8ff}.reply{color:#ff7fb8}
</style></head><body><div id="box"><canvas id="c"></canvas><div id="t"></div></div>
<script>
const q=new URLSearchParams(location.search);const SIZE=q.get('size')||'standard';
const W={compact:236,standard:340,full:420}[SIZE]||340,CH={compact:170,standard:200,full:260}[SIZE]||200;
const cv=document.getElementById('c');cv.width=W-20;cv.height=CH;const g=cv.getContext('2d');
let S={state:'idle',color:[25,211,255],level:0,lines:[]},t0=performance.now();
function ico(sub){const t=(1+Math.sqrt(5))/2;let v=[[-1,t,0],[1,t,0],[-1,-t,0],[1,-t,0],[0,-1,t],[0,1,t],[0,-1,-t],[0,1,-t],[t,0,-1],[t,0,1],[-t,0,-1],[-t,0,1]];
let f=[[0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],[1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],[3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],[4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1]];
const nz=a=>{const l=Math.hypot(...a);return a.map(x=>x/l)};v=v.map(nz);
for(let s=0;s<sub;s++){const c={},nf=[];const mid=(i,j)=>{const k=Math.min(i,j)+'_'+Math.max(i,j);if(!(k in c)){v.push(nz([0,1,2].map(n=>(v[i][n]+v[j][n])/2)));c[k]=v.length-1}return c[k]};
for(const [a,b,d] of f){const ab=mid(a,b),bc=mid(b,d),ca=mid(d,a);nf.push([a,ab,ca],[b,bc,ab],[d,ca,bc],[ab,bc,ca])}f=nf}
const e=new Set();for(const [a,b,c] of f)for(const [x,y] of [[a,b],[b,c],[c,a]])e.add(Math.min(x,y)+','+Math.max(x,y));
return {v,e:[...e].map(s=>s.split(',').map(Number))}}
const M=ico(2);
function draw(){const t=(performance.now()-t0)/1000,w=cv.width,h=cv.height,cx=w/2,cy=h/2,c=S.color,R=Math.min(w*.3,h*.42)*(1+.035*S.level);
g.clearRect(0,0,w,h);const rg=g.createRadialGradient(cx,cy,0,cx,cy,R*1.9);
rg.addColorStop(0,`rgba(${c},${.28+.28*S.level})`);rg.addColorStop(.5,`rgba(${c},.08)`);rg.addColorStop(1,`rgba(${c},0)`);
g.fillStyle=rg;g.beginPath();g.arc(cx,cy,R*1.9,0,7);g.fill();
const ay=t*.35,ax=.35,ca=Math.cos(ay),sa=Math.sin(ay),cb=Math.cos(ax),sb=Math.sin(ax);
const P=M.v.map(([x,y,z])=>{const x1=x*ca+z*sa,z1=-x*sa+z*ca,y1=y*cb-z1*sb,z2=y*sb+z1*cb;return [cx+x1*R,cy+y1*R,z2]});
g.fillStyle=`rgba(${c},.07)`;g.beginPath();g.arc(cx,cy,R,0,7);g.fill();g.lineWidth=1;
for(const [a,b] of M.e){const A=P[a],B=P[b],d=(A[2]+B[2])/2;g.strokeStyle=`rgba(${c},${Math.min(.85,.11+.43*(d+1)/2+.16*S.level)})`;g.beginPath();g.moveTo(A[0],A[1]);g.lineTo(B[0],B[1]);g.stroke()}
g.save();g.translate(cx,cy);g.rotate(1.2);g.strokeStyle=`rgba(${c},.35)`;g.beginPath();g.ellipse(0,0,R*1.45,R*.42,0,0,7);g.stroke();g.restore();
requestAnimationFrame(draw)}
function show(lines){const d=document.getElementById('t');d.innerHTML='';for(const [txt,k] of lines){const s=document.createElement('div');s.className=k;s.textContent=txt;d.appendChild(s)}}
async function poll(){try{const r=await fetch('/state',{cache:'no-store'});S=await r.json();show((S.lines||{})[SIZE]||[])}catch(e){show([['Trilion HUD: waiting for Trilion...','dim']])}setTimeout(poll,150)}
draw();poll();
</script></body></html>"""


class WebHud:
    """Serves the HUD to OBS (Browser Source) at http://127.0.0.1:<port>/?size=compact|standard|full"""

    def __init__(self, port=17655):
        self.port = port
        self.httpd = None
        self._payload = b"{}"
        self._lock = threading.Lock()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/"

    def update(self, snap):
        data = dict(snap)
        data["lines"] = {sz: [[t, k] for t, k in hud_lines(snap, sz)] for sz in ("compact", "standard", "full")}
        raw = json.dumps(data, default=str).encode("utf-8")
        with self._lock:
            self._payload = raw

    def _page(self, query):
        size = "standard"
        for part in query.split("&"):
            if part.startswith("size="):
                size = part[5:]
        w = {"compact": 236, "standard": 340, "full": 420}.get(size, 340)
        bg = "transparent" if "bg=0" in query else "rgba(4,14,32,.62)"
        return PAGE.replace("__W__", str(w)).replace("__BG__", bg).encode("utf-8")

    def start(self):
        hud = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path, _, query = self.path.partition("?")
                if path == "/state":
                    with hud._lock:
                        body = hud._payload
                    self._send(200, body, "application/json")
                elif path in ("/", "/index.html"):
                    self._send(200, hud._page(query), "text/html; charset=utf-8")
                else:
                    self._send(404, b"not found", "text/plain")

        last = None
        for port in ([self.port + i for i in range(10)] if self.port else [0]):
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", port), H)   # this PC only
                break
            except OSError as e:
                last = e
        if not self.httpd:
            raise last
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        log.info("HUD web source on %s", self.url)
        return self.url

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
