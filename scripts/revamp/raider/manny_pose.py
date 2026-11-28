"""Pose the Manny-axis Raider rig in a dumped Manny frame, as Unreal's one-to-one retarget would.

pose_ue5_anim_test.py's method: Manny's component rotations, this character's bone lengths, pelvis height scaled.
Shared by review_closeups.py and plate_check.py.
"""
import numpy as np
from mathutils import Matrix, Quaternion, Vector

M_UE = np.diag([1.0, -1.0, 1.0])
P_AX = np.diag([1.0, -1.0, 1.0])


class MannyPoser:
    def __init__(self, rig, manny):
        self.rig = rig
        self.parents = {b['name']: b['parent'] for b in manny['bones']}
        self.manny_ref = {b['name']: np.array(b['pos']) for b in manny['bones']}
        self.rest = {b.name: (M_UE @ np.array(b.matrix_local.to_3x3()) @ P_AX, M_UE @ np.array(b.head_local) * 100.0)
                     for b in rig.data.bones}
        self.rest['root'] = (np.eye(3), np.zeros(3))
        self.order = []
        for n in self.parents:
            self._visit(n)

    def _visit(self, n):
        if n not in self.order:
            if self.parents[n]:
                self._visit(self.parents[n])
            self.order.append(n)

    def apply(self, pose, view_layer):
        """Pose the rig (None is the bind pose); returns the pelvis position in metres."""
        rest, parents = self.rest, self.parents
        G, Pp = {}, {}
        scale = rest['pelvis'][1][2] / self.manny_ref['pelvis'][2]
        for n in self.order:
            if pose is None:
                G[n], Pp[n] = rest[n]
                continue
            src = pose['bones'][n]
            G[n] = np.array(Quaternion((src['quat'][3], *src['quat'][:3])).to_matrix())
            p = parents[n]
            if p is None:
                Pp[n] = np.zeros(3)
            elif n == 'pelvis':
                Pp[n] = np.array(src['pos']) * scale
            else:
                Pp[n] = Pp[p] + G[p] @ (rest[p][0].T @ (rest[n][1] - rest[p][1]))
        for n in self.order:
            if n != 'root' and n in self.rig.pose.bones:
                mat = Matrix((M_UE @ G[n] @ P_AX).tolist()).to_4x4()
                mat.translation = Vector(M_UE @ Pp[n] / 100.0)
                self.rig.pose.bones[n].matrix = mat
                view_layer.update()
        return Vector(M_UE @ Pp['pelvis'] / 100.0)
