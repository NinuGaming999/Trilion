// Rig: world-axis posing for a skinned skeleton, independent of each bone's local axes.
// rot(name, x, y, z) adds a rotation about WORLD axes (relative to the rest pose). Character faces +Z, Y is up:
//   +x = nod forward/down   +y = turn toward +X (her left)   +z = roll toward her right
// The FBX has one skeleton copy per mesh, so every pose is applied to all copies of a bone.
export class Rig {
  constructor(T, root) {
    this.T = T;
    this.bones = {};
    const seen = new Set();
    root.traverse((m) => {
      if (m.isSkinnedMesh) m.skeleton.bones.forEach((b) => {
        if (seen.has(b)) return;
        seen.add(b);
        (this.bones[b.name] || (this.bones[b.name] = [])).push(b);
      });
    });
    root.updateMatrixWorld(true);
    this.rest = new Map();
    for (const list of Object.values(this.bones)) for (const b of list) {
      const wq = b.getWorldQuaternion(new T.Quaternion());
      const pinv = b.parent ? b.parent.matrixWorld.clone().invert() : new T.Matrix4();
      this.rest.set(b, { q: b.quaternion.clone(), p: b.position.clone(), wq, wqi: wq.clone().invert(), pinv });
    }
    this.acc = {}; this.off = {};
    this._e = new T.Euler(0, 0, 0, 'YXZ'); this._l = new T.Quaternion();
  }
  has(n) { return !!this.bones[n]; }
  reset() { this.acc = {}; this.off = {}; }
  rot(n, x = 0, y = 0, z = 0) {
    if (!this.bones[n] || (!x && !y && !z)) return;
    const q = new this.T.Quaternion().setFromEuler(this._e.set(x, y, z, 'YXZ'));
    this.acc[n] = this.acc[n] ? q.multiply(this.acc[n]) : q;
  }
  move(n, x = 0, y = 0, z = 0) {   // offset in the bone's parent space, model units
    if (!this.bones[n]) return;
    const o = this.off[n] || (this.off[n] = new this.T.Vector3());
    o.x += x; o.y += y; o.z += z;
  }
  moveWorld(n, x = 0, y = 0, z = 0) {   // metres along WORLD axes (rest orientation), converted to parent-local units
    const list = this.bones[n];
    if (!list || (!x && !y && !z)) return;
    const pinv = this.rest.get(list[0]).pinv;
    const tl = new this.T.Vector3(x, y, z).applyMatrix4(pinv).sub(new this.T.Vector3(0, 0, 0).applyMatrix4(pinv));
    this.move(n, tl.x, tl.y, tl.z);
  }
  apply() {
    for (const [n, list] of Object.entries(this.bones)) {
      const a = this.acc[n], o = this.off[n];
      for (const b of list) {
        const r = this.rest.get(b);
        if (a) { this._l.copy(r.wqi).multiply(a).multiply(r.wq); b.quaternion.copy(r.q).multiply(this._l); } else b.quaternion.copy(r.q);
        if (o) b.position.copy(r.p).add(o); else b.position.copy(r.p);
      }
    }
  }
}

export const B = {
  hips: 'ValveBipedBip01_Spine', spine1: 'ValveBipedBip01_Spine1', spine2: 'ValveBipedBip01_Spine2', chest: 'ValveBipedBip01_Spine4',
  neck: 'ValveBipedBip01_Neck1', head: 'ValveBipedBip01_Head1',
  clavL: 'ValveBipedBip01_L_Clavicle', armL: 'ValveBipedBip01_L_UpperArm', foreL: 'ValveBipedBip01_L_Forearm', handL: 'ValveBipedBip01_L_Hand',
  clavR: 'ValveBipedBip01_R_Clavicle', armR: 'ValveBipedBip01_R_UpperArm', foreR: 'ValveBipedBip01_R_Forearm', handR: 'ValveBipedBip01_R_Hand',
  thighL: 'ValveBipedBip01_L_Thigh', thighR: 'ValveBipedBip01_R_Thigh',
  eyeL: '+EyeBone_L_A02', eyeR: '+EyeBone_R_A02', jaw: '+ToothBone_D_A01', jawU: '+ToothBone_U_A01',
};
