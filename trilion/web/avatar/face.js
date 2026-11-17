// Face: eyelids, glare/smile shapes, an animated mouth and eye gaze for a model with no facial morph targets.
// Lids and mouth are drawn by a shader patched into the face material, in HEAD coordinates (so they follow the head).
// The pupils belong to the hair mesh (weighted to the eye bones): they are moved for gaze and clipped by the lids.
import { B } from './rig.js';

const GLSL_COMMON = `
uniform mat4 uHeadInv; uniform mat3 uRest3; uniform vec3 uEyeL; uniform vec3 uEyeR; uniform vec2 uHalfL; uniform vec2 uHalfR;
uniform vec3 uLidL; uniform vec3 uLidR;      // x = closed 0..1, y = tilt (+ = angry), z = lower lid raise 0..1
uniform vec3 uHairTint; uniform float uDebug; uniform float uSideL; uniform vec3 uSkin; uniform vec3 uSkinR; uniform vec3 uLash;
uniform vec3 uMouth;                          // x = open, y = width, z = smile
varying vec3 vWp; varying float vIris;
bool lidHit(vec3 d, vec2 H, vec3 L, float s, out float line) {
  line = 0.0;
  if (abs(d.x) > H.x || abs(d.y) > H.y || abs(d.z) > 0.03) return false;
  float x = d.x / H.x, top = H.y, bot = -H.y * 0.78;
  float inner = -x * s;
  float edge = mix(top, bot, L.x) - L.y * 0.55 * H.y * inner - 0.16 * H.y * L.x * (1.0 - x * x);
  float lowEdge = bot + L.z * H.y * 0.9;
  float w = H.y * 0.09;
  float shape = 1.0 - pow(abs(x), 4.0);
  line = (1.0 - smoothstep(0.0, w, abs(d.y - edge))) * step(0.02, L.x + abs(L.y)) * shape;
  line = max(line, (1.0 - smoothstep(0.0, w * 0.8, abs(d.y - lowEdge))) * step(0.02, L.z) * shape);
  return d.y > edge || d.y < lowEdge;
}`;

export class Face {
  constructor(T, root, rig) {
    this.T = T; this.rig = rig;
    this.u = {
      uHeadInv: { value: new T.Matrix4() }, uRest3: { value: new T.Matrix3() },
      uEyeL: { value: new T.Vector3() }, uEyeR: { value: new T.Vector3() },
      uHalfL: { value: new T.Vector2(0.014, 0.012) }, uHalfR: { value: new T.Vector2(0.014, 0.012) }, uSideL: { value: 1 },
      uLidL: { value: new T.Vector3() }, uLidR: { value: new T.Vector3() },
      uSkin: { value: new T.Vector3(0.9, 0.6, 0.5) }, uSkinR: { value: new T.Vector3(0.9, 0.6, 0.5) },
      uLash: { value: new T.Vector3(0.1, 0.05, 0.06) }, uMouth: { value: new T.Vector3() },
      uHairTint: { value: new T.Vector3(0.50, 0.52, 0.57) }, uDebug: { value: 0 },
    };
    let faceMesh, hairMesh;
    root.traverse((m) => { if (m.isSkinnedMesh) { if (m.material.name === 'face') faceMesh = m; if (m.material.name === 'hair') hairMesh = m; } });
    if (!faceMesh || !hairMesh) throw new Error('face/hair meshes not found');
    this.faceMesh = faceMesh; this.hairMesh = hairMesh;
    this.headBone = rig.bones[B.head][0];                       // skeleton copies are posed identically
    root.updateMatrixWorld(true);
    const hm = this.headBone.matrixWorld.clone();
    this.u.uRest3.value.setFromMatrix4(hm);
    this.eyeBoxes = this.calibrate(faceMesh, hm);
    this._markIris(hairMesh);
    this._patch(faceMesh.material, 'face');
    this._patch(hairMesh.material, 'hair');
    this.gazeBones = ['+EyeBone_L_A02', '+EyeBone_R_A02'];
  }

  // Find the two white eye sockets in the face texture, then use the mesh's own UV->world mapping to get each socket's
  // centre (head-local), size (metres) and the skin colour just below it. No guessing where the eye bones sit.
  calibrate(mesh, hm) {
    const T = this.T, img = mesh.material.map.image, W = img.width, H = img.height;
    const c = document.createElement('canvas'); c.width = W; c.height = H;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const px = g.getImageData(0, 0, W, H).data;
    const sock = [[1e9, 1e9, -1, -1], [1e9, 1e9, -1, -1]];
    for (let y = Math.floor(0.36 * H); y < 0.54 * H; y++) for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      if (px[i] > 238 && px[i + 1] > 238 && px[i + 2] > 238) {
        const s = sock[x < W / 2 ? 0 : 1];
        s[0] = Math.min(s[0], x); s[1] = Math.min(s[1], y); s[2] = Math.max(s[2], x); s[3] = Math.max(s[3], y);
      }
    }
    const uv = mesh.geometry.attributes.uv, pos = mesh.geometry.attributes.position, p = new T.Vector3();
    mesh.updateMatrixWorld(true);
    const lin = (v) => Math.pow(v / 255, 2.2), out = [];
    for (const s of sock) {
      if (s[2] < 0) throw new Error('eye socket not found in the face texture');
      const u0 = s[0] / W - 0.004, u1 = s[2] / W + 0.004, v0 = 1 - s[3] / H - 0.008, v1 = 1 - s[1] / H + 0.026;   // + room for the upper lash line
      const cu = (u0 + u1) / 2, cv = (v0 + v1) / 2, rows = [];
      for (let i = 0; i < uv.count; i++) {
        if (Math.abs(uv.getX(i) - cu) < 0.14 && Math.abs(uv.getY(i) - cv) < 0.14) { p.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld); rows.push([uv.getX(i), uv.getY(i), p.x, p.y, p.z]); }
      }
      const fit = (col) => {                              // least squares: w = a + b*u + c*v
        let n = rows.length, Su = 0, Sv = 0, Suu = 0, Suv = 0, Svv = 0, Sw = 0, Suw = 0, Svw = 0;
        for (const r of rows) { const u = r[0], v = r[1], w = r[col]; Su += u; Sv += v; Suu += u * u; Suv += u * v; Svv += v * v; Sw += w; Suw += u * w; Svw += v * w; }
        const M = new T.Matrix3().set(n, Su, Sv, Su, Suu, Suv, Sv, Suv, Svv);
        return new T.Vector3(Sw, Suw, Svw).applyMatrix3(M.invert());
      };
      const fx = fit(2), fy = fit(3), fz = fit(4);
      const at = (u, v) => new T.Vector3(fx.x + fx.y * u + fx.z * v, fy.x + fy.y * u + fy.z * v, fz.x + fz.y * u + fz.z * v);
      const wc = at(cu, cv), wa = at(u0, v0), wb = at(u1, v1);
      const x0 = Math.floor((s[0] + s[2]) / 2 - 14), y0 = Math.floor(s[3] + 16);
      let r = 0, gg = 0, b = 0, n = 0;
      for (let y = y0; y < y0 + 8; y++) for (let x = x0; x < x0 + 28; x++) { const i = (y * W + x) * 4; r += px[i]; gg += px[i + 1]; b += px[i + 2]; n++; }
      out.push({ center: wc.clone().applyMatrix4(hm.clone().invert()), half: [Math.abs(wb.x - wa.x) / 2, Math.abs(wb.y - wa.y) / 2], worldX: wc.x, n: rows.length, skin: new T.Vector3(lin(r / n), lin(gg / n), lin(b / n)) });
    }
    out.sort((a, b) => b.worldX - a.worldX);               // out[0] = her left (world +X)
    this.u.uEyeL.value.copy(out[0].center); this.u.uEyeR.value.copy(out[1].center);
    this.u.uHalfL.value.set(...out[0].half); this.u.uHalfR.value.set(...out[1].half);
    this.u.uSkin.value.copy(out[0].skin); this.u.uSkinR.value.copy(out[1].skin);
    return out;
  }

  _markIris(mesh) {
    const g = mesh.geometry, si = g.attributes.skinIndex, sw = g.attributes.skinWeight, n = si.count;
    const eye = new Set(); mesh.skeleton.bones.forEach((b, i) => { if (/EyeBone_[LR]_A02$/.test(b.name)) eye.add(i); });
    const a = new Float32Array(n);
    for (let i = 0; i < n; i++) for (let k = 0; k < 4; k++) if (sw.getComponent(i, k) > 0.3 && eye.has(si.getComponent(i, k))) a[i] = 1;
    g.setAttribute('aIris', new this.T.BufferAttribute(a, 1));
  }

  _patch(mat, kind) {
    const u = this.u;
    mat.onBeforeCompile = (sh) => {
      Object.assign(sh.uniforms, u);
      sh.vertexShader = sh.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vWp; varying float vIris; ' + (kind === 'hair' ? 'attribute float aIris;' : ''))
        .replace('#include <project_vertex>', '#include <project_vertex>\nvWp = (modelMatrix * vec4(transformed, 1.0)).xyz; vIris = ' + (kind === 'hair' ? 'aIris' : '0.0') + ';');
      let f = sh.fragmentShader.replace('#include <common>', '#include <common>\n' + GLSL_COMMON);
      const body = `
        vec3 pl = (uHeadInv * vec4(vWp, 1.0)).xyz;
        vec3 dL = uRest3 * (pl - uEyeL), dR = uRest3 * (pl - uEyeR);
        float lnL, lnR; bool hitL = lidHit(dL, uHalfL, uLidL, uSideL, lnL), hitR = lidHit(dR, uHalfR, uLidR, -uSideL, lnR);`;
      if (kind === 'face') {
        f = f.replace('#include <map_fragment>', `#include <map_fragment>
          ${body}
          vec3 sc = pow(max(diffuseColor.rgb, vec3(0.0)), vec3(0.4545));
          float skinness = smoothstep(0.50, 0.60, dot(sc, vec3(0.299, 0.587, 0.114))) * smoothstep(0.04, 0.09, sc.r - sc.b);
          if (hitL) diffuseColor.rgb = mix(diffuseColor.rgb, uSkin, 1.0 - skinness);
          if (hitR) diffuseColor.rgb = mix(diffuseColor.rgb, uSkinR, 1.0 - skinness);
          diffuseColor.rgb = mix(diffuseColor.rgb, uLash, max(lnL, lnR));
          // no hair on the back/top of the head in this model: show hair colour instead of bare scalp
          vec3 dh = uRest3 * pl;
          float sc1 = smoothstep(0.075, 0.095, dh.y) * (1.0 - smoothstep(0.050, 0.066, dh.z));
          float sc2 = (1.0 - smoothstep(-0.045, -0.030, dh.z)) * smoothstep(-0.040, -0.015, dh.y);
          float scalp = max(sc1, sc2);
          diffuseColor.rgb = mix(diffuseColor.rgb, uHairTint * (0.75 + 0.25 * (1.0 - scalp)), scalp);
          // mouth (texture space): dark opening, teeth hint
          vec2 mp = (vMapUv - vec2(0.5105, 0.3345)) / vec2(0.034 * (1.0 + 0.35 * uMouth.y), 0.03);
          float open = uMouth.x;
          if (open > 0.04) {
            float h = 0.12 + 0.88 * open;
            float e = mp.x * mp.x + (mp.y / h) * (mp.y / h);
            if (e < 1.0) {
              vec3 inside = mix(vec3(0.30, 0.06, 0.08), vec3(0.12, 0.02, 0.03), smoothstep(0.0, 1.0, e));
              float teeth = smoothstep(0.35, 0.55, mp.y / h) * step(0.2, open) * (1.0 - e);
              inside = mix(inside, vec3(0.93, 0.9, 0.88), teeth * 0.85);
              diffuseColor.rgb = mix(inside, diffuseColor.rgb, smoothstep(0.82, 1.0, e));
            }
          }
          diffuseColor.rgb += vec3(0.05, 0.0, 0.0) * uMouth.z;
          if (uDebug > 0.5) { if (abs(dL.x) < uHalfL.x && abs(dL.y) < uHalfL.y && abs(dL.z) < 0.05) diffuseColor.rgb = vec3(0.0, 1.0, 0.0); if (abs(dR.x) < uHalfR.x && abs(dR.y) < uHalfR.y && abs(dR.z) < 0.05) diffuseColor.rgb = vec3(1.0, 0.0, 1.0); }`);
      } else {
        f = f.replace('#include <map_fragment>', `#include <map_fragment>
          ${body}
          if (vIris > 0.5 && (hitL || hitR)) discard;`);
      }
      sh.fragmentShader = f;
    };
    mat.needsUpdate = true;
  }

  // per frame: lids {closed,tilt,low} per eye, mouth {open,width,smile}, gaze {x,y} in -1..1
  update(p) {
    const u = this.u;
    this.headBone.updateMatrixWorld(true);
    u.uHeadInv.value.copy(this.headBone.matrixWorld).invert();
    u.uLidL.value.set(p.lidL.closed, p.lidL.tilt, p.lidL.low);
    u.uLidR.value.set(p.lidR.closed, p.lidR.tilt, p.lidR.low);
    u.uMouth.value.set(p.mouth.open, p.mouth.width, p.mouth.smile);
    const gx = Math.max(-1, Math.min(1, p.gaze.x)), gy = Math.max(-1, Math.min(1, p.gaze.y));
    for (const n of this.gazeBones) this.rig.moveWorld(n, gx * 0.0028, gy * 0.0012, 0);   // tiny travel: stays inside the socket
  }
}
