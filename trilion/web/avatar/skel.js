// The FBX loads as one skeleton copy per mesh, and in the hair/body/dress copies a bone's parents are duplicate nodes that are
// NOT part of the skeleton, so a spine/neck rotation never reaches the head or hair (only the face copy is a clean chain).
// Result: hair, body and head drift apart as soon as she moves. Fix: drive every mesh from ONE set of bones (the cleanest copy)
// and keep each mesh's own bone order and inverse bind matrices, so nothing about the skinning data changes.
export function unifySkeletons(T, root, tolPos = 0.005, tolAng = 0.02) {
  const meshes = [];
  root.traverse((o) => { if (o.isSkinnedMesh) meshes.push(o); });
  const info = { meshes: meshes.length, unified: 0, skipped: [], ref: null };
  if (meshes.length < 2) return info;
  root.updateMatrixWorld(true);
  const chainScore = (m) => { const s = new Set(m.skeleton.bones); return m.skeleton.bones.filter((b) => b.parent && s.has(b.parent)).length; };
  const ref = meshes.reduce((a, b) => (chainScore(b) > chainScore(a) ? b : a));
  info.ref = ref.material && ref.material.name;
  const byName = new Map(ref.skeleton.bones.map((b) => [b.name, b]));
  const p1 = new T.Vector3(), p2 = new T.Vector3(), q1 = new T.Quaternion(), q2 = new T.Quaternion();
  for (const m of meshes) {
    if (m === ref) continue;
    const bones = m.skeleton.bones.map((b) => byName.get(b.name));
    if (bones.some((b) => !b)) { info.skipped.push((m.material && m.material.name) + ': bone names differ'); continue; }
    let bad = 0;                                              // same bind pose? (inverse bind matrices only stay valid if so)
    m.skeleton.bones.forEach((b, i) => {
      b.getWorldPosition(p1); bones[i].getWorldPosition(p2); b.getWorldQuaternion(q1); bones[i].getWorldQuaternion(q2);
      if (p1.distanceTo(p2) > tolPos || 2 * Math.acos(Math.min(1, Math.abs(q1.dot(q2)))) > tolAng) bad++;
    });
    if (bad) { info.skipped.push((m.material && m.material.name) + ': ' + bad + ' bones differ at rest'); continue; }
    const inverses = m.skeleton.boneInverses.map((x) => x.clone());
    m.skeleton.dispose();
    m.bind(new T.Skeleton(bones, inverses), m.bindMatrix.clone());
    info.unified++;
  }
  return info;
}
