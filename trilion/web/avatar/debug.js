// Press D on the avatar page: play any clip / emotion / pose, slow time down, change movement intensity, watch fps + quality level.
import { CLIPS, EMOTIONS, ARM_POSES } from './anim.js';

export function buildDebug(A) {
  const d = document.createElement('div'); d.id = 'dbg';
  d.style.cssText = 'position:fixed;left:10px;top:44px;z-index:30;width:290px;max-height:80vh;overflow:auto;padding:10px;border:1px solid rgba(40,150,255,.5);border-radius:10px;background:rgba(6,18,40,.9);color:#cfe6ff;font:11px Inter,system-ui,sans-serif;display:none';
  const css = 'margin:2px;padding:3px 7px;border:1px solid rgba(40,150,255,.5);border-radius:6px;background:rgba(10,40,90,.7);color:#cfe6ff;cursor:pointer;font:11px Inter,system-ui,sans-serif';
  const row = (t) => { const e = document.createElement('div'); e.style.cssText = 'margin:6px 0 2px;color:#19d3ff;letter-spacing:.08em;text-transform:uppercase;font-size:10px'; e.textContent = t; d.appendChild(e); };
  const btns = (names, fn) => { const w = document.createElement('div'); for (const n of names) { const b = document.createElement('button'); b.style.cssText = css; b.textContent = n; b.onclick = () => fn(n); w.appendChild(b); } d.appendChild(w); };
  const slider = (label, min, max, step, val, fn) => {
    const w = document.createElement('label'); w.style.cssText = 'display:flex;align-items:center;gap:8px;margin:4px 0';
    const s = document.createElement('input'); s.type = 'range'; s.min = min; s.max = max; s.step = step; s.value = val; s.style.flex = '1';
    const v = document.createElement('span'); v.style.width = '34px'; v.textContent = (+val).toFixed(2);
    s.oninput = () => { v.textContent = (+s.value).toFixed(2); fn(+s.value); };
    w.append(label, s, v); d.appendChild(w); return s;
  };
  const stat = document.createElement('div'); stat.style.cssText = 'font-family:Consolas,monospace;margin-bottom:4px'; d.appendChild(stat);
  row('movement');
  slider('intensity', 0.3, 1.6, 0.05, A.anim ? A.anim.intensity : 1, (v) => { A.anim.intensity = v; });
  slider('time', 0.1, 1, 0.05, 1, (v) => { A.timeScale = v; });
  row('clips'); btns(Object.keys(CLIPS), (n) => A.anim.play(n, { side: Math.random() < 0.5 ? -1 : 1, power: 1 }));
  row('emotions'); btns(Object.keys(EMOTIONS), (n) => A.anim.setEmotion(n, 5));
  row('arm poses'); btns(Object.keys(ARM_POSES), (n) => A.anim.poseArms(n, 5));
  row('view'); btns(['full', 'bust', 'face'], (n) => A.setView(n));
  const g = document.createElement('button'); g.style.cssText = css; g.textContent = 'toggle glow (G)'; g.onclick = () => A.setGlow(!A.glow); d.appendChild(g);
  document.body.appendChild(d);
  let last = 0;
  return {
    toggle() { d.style.display = d.style.display === 'none' ? 'block' : 'none'; },
    tick(now) { if (d.style.display === 'none' || now - last < 0.5) return; last = now; stat.textContent = 'fps ' + A.perf.fps.toFixed(0) + '  quality ' + A.perf.level + '  glow ' + (A.glow ? 'on' : 'off') + '  clips ' + A.anim.clips.length; },
  };
}
