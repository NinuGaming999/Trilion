// Vibrant look: a colour-grade + fresnel rim + soft sheen injected at the end of every material's fragment shader
// (chained after face.js's own patch), plus an aura halo behind her. Pure shading: no geometry or animation changes.
const GRADE = `
  {
    vec3 c = gl_FragColor.rgb;
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
    c = mix(vec3(lum), c, uSat);                                             // richer colour
    c = mix(c * uShadowTint, c, smoothstep(0.04, 0.45, lum));                // cool, saturated shadows
    c *= mix(vec3(1.0), uWarm, smoothstep(0.25, 0.9, lum));                  // warm highlights
    vec3 N = normalize(vNormal), V = normalize(vViewPosition);
    float nv = clamp(dot(N, V), 0.0, 1.0);
    float fr = pow(1.0 - nv, 2.6);
    c += uRim.rgb * fr * uRim.a * (0.35 + 0.65 * smoothstep(0.0, 0.5, lum + 0.25)); // pyro rim light
    vec3 H = normalize(V + normalize(vec3(0.35, 0.8, 0.6)));
    c += uSheen * pow(clamp(dot(N, H), 0.0, 1.0), 36.0) * smoothstep(0.15, 0.6, lum);   // soft glossy sheen
    c = c * (1.0 + uPop * (c - vec3(lum)));                                  // local colour pop
    float rd = clamp((c.r - max(c.g, c.b) * 1.5) * 3.0, 0.0, 1.0);          // red details (gems, irises, lining) emit light
    c += vec3(1.0, 0.16, 0.10) * rd * uGlow * (0.45 + lum);
    gl_FragColor.rgb = max(c, vec3(0.0));
  }`;

export function makeLook(THREE) {
  const U = {
    uSat: { value: 1.32 }, uShadowTint: { value: new THREE.Vector3(0.86, 0.84, 1.12) }, uWarm: { value: new THREE.Vector3(1.06, 1.0, 0.94) },
    uRim: { value: new THREE.Vector4(1.0, 0.25, 0.2, 0.55) }, uSheen: { value: 0.07 }, uPop: { value: 0.25 }, uGlow: { value: 1.0 },
  };
  const hook = (mat) => {
    const prev = mat.onBeforeCompile, prevKey = mat.customProgramCacheKey ? mat.customProgramCacheKey.bind(mat) : () => '';
    mat.onBeforeCompile = (sh, r) => {
      if (prev) prev.call(mat, sh, r);
      Object.assign(sh.uniforms, U);
      sh.fragmentShader = sh.fragmentShader
        .replace('#include <common>', '#include <common>\nuniform float uSat, uSheen, uPop, uGlow; uniform vec3 uShadowTint, uWarm; uniform vec4 uRim;')
        .replace('#include <opaque_fragment>', '#include <opaque_fragment>\n' + GRADE);
    };
    mat.customProgramCacheKey = () => prevKey() + '|look1';
    mat.needsUpdate = true;
  };
  return {
    U,
    apply(root) {
      const seen = new Set();
      root.traverse((o) => {
        if (!o.isMesh) return;
        for (const m of (Array.isArray(o.material) ? o.material : [o.material])) {
          if (seen.has(m)) continue; seen.add(m);
          if (m.isMeshPhongMaterial) { m.shininess = Math.max(m.shininess || 0, 30); m.specular?.setScalar(0.10); }
          if (m.map) m.map.anisotropy = 8;
          hook(m);
        }
      });
    },
    // anger/aura -> rim colour & strength (calm: cool cyan-violet, angry: hot red-orange)
    update(t, aura, anger) {
      const a = Math.min(1, aura), k = Math.min(1, anger);
      const r = 0.35 + 0.65 * k, g = 0.55 - 0.35 * k, b = 1.0 - 0.8 * k;
      U.uRim.value.set(r, g, b, 0.6 + 1.0 * a + 0.06 * Math.sin(t * 2.0));
      U.uGlow.value = 1.1 + 1.6 * a + 0.9 * k + 0.12 * Math.sin(t * 2.6);
    },
  };
}

// big soft additive glow behind her, tinted by mood
export function makeHalo(THREE, scene) {
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.CustomBlending, blendEquation: THREE.AddEquation,
    blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneFactor,   // light only: never an opaque box
    uniforms: { uCol: { value: new THREE.Color(0.2, 0.55, 1.0) }, uA: { value: 0.3 }, uT: { value: 0 } },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: `varying vec2 vUv; uniform vec3 uCol; uniform float uA, uT;
      void main(){
        vec2 m = (vUv - 0.5) * vec2(5.2, 4.4);                                   // metres from the plane centre (plane centre is at y = 1.25)
        float g = exp(-pow(length(vec2(m.x, (m.y + 0.1) * 0.62)) / 0.72, 2.0));  // aura around her: taller than wide
        float hr = length(m - vec2(0.0, 0.42));                                  // ring behind the head
        float ring = exp(-pow((hr - 0.46 - 0.012 * sin(uT * 1.3)) / 0.035, 2.0));
        float soft = exp(-pow((hr - 0.46) / 0.17, 2.0)) * 0.35;
        vec3 c = uCol * (g * 0.8 + ring * 1.4 + soft) * uA; gl_FragColor = vec4(c, pow(max(c.r, max(c.g, c.b)), 0.4545));
        #include <colorspace_fragment>
      }`,
  });
  const m = new THREE.Mesh(new THREE.PlaneGeometry(5.2, 4.4), mat);
  m.position.set(0, 1.25, -1.1); m.renderOrder = -1; m.frustumCulled = false; scene.add(m);
  return {
    mesh: m,
    update(t, aura, anger, camYaw) {
      const k = Math.min(1, anger), a = Math.min(1, aura);
      mat.uniforms.uCol.value.setRGB(0.18 + 0.9 * k, 0.55 - 0.3 * k, 1.0 - 0.85 * k);
      mat.uniforms.uA.value = 0.14 + 0.4 * a + 0.015 * Math.sin(t * 1.7);
      mat.uniforms.uT.value = t;
      m.rotation.y = camYaw * 0.0;                 // stays facing the camera plane; orbit limits keep it behind her
    },
  };
}
