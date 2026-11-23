"""A character's own calibration of the Manny retargeter, and a per-frame gait layer (Unreal editor Python).

The Aether Wars' installer offsets the target retarget pose to Manny's reference rotations bone for bone, so every
clip copies Manny's joint angles exactly (its verification reports < 0.01 degrees). On a body built differently that
exact copy shrugs the shoulders (Character02) or tips the torso forward (Remora). Two recipe settings correct it
(docs/GAME_REVIEW.md, "Retarget pose and gait style"; proved on Character02 2026-11-07 and Remora 2026-11-09):

retarget_pose (applied to the retargeter before the batch, so it reaches every clip):
  clavicles 'own_rest': the collarbones keep the character's modelled rest; the upper arms are re-offset so the arms
      still hang in Manny's direction (Character02's candidate B). clavicle_drop lowers them further (degrees).
  pitch {bone: degrees}: tilts spine/neck bones about the body's left-right axis (+ bends forward).
gait_style (applied to retargeted sequences after the batch; pattern -> operations, first match wins):
  hip_roll / hip_yaw: pelvis side tilt and turn about their clip mean, scaled; the chest is held and the legs are
      re-solved by two-bone IK so the feet land where they did.
  hip_shift: the pelvis' side-to-side travel (relative to the root) scaled.
  narrow_cm: each foot moved toward the midline (step width), legs re-solved, soles kept. A planted foot keeps the
      full offset; the foot in the air swings out by the same amount as it passes the planted one (swing_clear,
      1 = fully, 0 = constant offset), so the pair keep their stock gap at the pass: Remora's boots are about 12 cm
      across and a constant 3 cm put the passing boot through the standing one.
  arm_in: upper arms turned toward the body about the forward axis (degrees). upright: chest tilted back (degrees).
  finger_relax: finger rotations blended toward the character's own relaxed hand (her retargeted MM_Idle at 1 s):
      Manny's spread fingers in the jump and fall read as claws on Remora.
  elbow_bend: the elbow's bend scaled about its own hinge (< 1 opens it). Remora's short forearms carry Manny's jog
      hands about 4 cm closer to her face than his; from the front they covered her mouth.
IK bones the retargeter pins to hands and feet follow their bones. Body axes are Manny's (the clips carry his
global orientation; the character's own hip line can be skewed a few degrees).
"""
import fnmatch
import math

import unreal

PIN_DEFAULT = [('hand_r', 'ik_hand_gun'), ('hand_l', 'ik_hand_l'), ('hand_r', 'ik_hand_r'),
               ('foot_l', 'ik_foot_l'), ('foot_r', 'ik_foot_r')]
NEXT = {'spine_01': 'spine_02', 'spine_02': 'spine_03', 'spine_03': 'spine_04', 'spine_04': 'spine_05',
        'spine_05': 'neck_01', 'neck_01': 'neck_02', 'neck_02': 'head'}
TARGET = unreal.RetargetSourceOrTarget.TARGET


# ---------- vectors and quaternions (UE: child global = parent * local; q1 * q2 applies q2 first) ----------
def _v(x, y, z):
    return unreal.Vector(x, y, z)


def dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z


def cross(a, b):
    return _v(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)


def length(v):
    return math.sqrt(dot(v, v))


def unit(v):
    n = length(v)
    return _v(v.x / n, v.y / n, v.z / n)


def scale(v, s):
    return _v(v.x * s, v.y * s, v.z * s)


def axis_angle(axis, radians):
    s = math.sin(radians / 2)
    return unreal.Quat(axis.x * s, axis.y * s, axis.z * s, math.cos(radians / 2))


def deg_axis(axis, degrees):
    return axis_angle(axis, math.radians(degrees))


def rotvec(q):
    x, y, z, w = q.x, q.y, q.z, q.w
    if w < 0:
        x, y, z, w = -x, -y, -z, -w
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-12:
        return _v(0, 0, 0)
    angle = 2 * math.atan2(n, w)
    return _v(x / n * angle, y / n * angle, z / n * angle)


def from_rotvec(v):
    a = length(v)
    return unreal.Quat(0, 0, 0, 1) if a < 1e-12 else axis_angle(scale(v, 1 / a), a)


def from_to(a, b):
    a, b = unit(a), unit(b)
    c = cross(a, b)
    s = length(c)
    if s < 1e-9:
        return unreal.Quat(0, 0, 0, 1)
    return axis_angle(scale(c, 1 / s), math.atan2(s, dot(a, b)))


def mean_quat(qs):
    ref = qs[0]
    x = y = z = w = 0.0
    for q in qs:
        sgn = 1 if (q.x * ref.x + q.y * ref.y + q.z * ref.z + q.w * ref.w) >= 0 else -1
        x, y, z, w = x + sgn * q.x, y + sgn * q.y, z + sgn * q.z, w + sgn * q.w
    n = math.sqrt(x * x + y * y + z * z + w * w)
    return unreal.Quat(x / n, y / n, z / n, w / n)


class Xf:      # position + rotation (unit scale): a component-space global or a parent-space local
    def __init__(self, pos, rot):
        self.pos, self.rot = pos, rot

    def compose(self, local):
        return Xf(self.pos + self.rot.rotate_vector(local.pos), self.rot * local.rot)

    def relative(self, child):
        return Xf(self.rot.unrotate_vector(child.pos - self.pos), self.rot.inversed() * child.rot)


# ---------- skeleton facts ----------
def skeleton_info(mesh):
    """Bone names (parents first), parent map, and the reference pose in component space."""
    actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
        unreal.SkeletalMeshActor, unreal.Vector(0, 0, -100000), transient=True)
    try:
        comp = actor.skeletal_mesh_component
        comp.set_skeletal_mesh_asset(mesh)
        names, parents, pose = [], {}, {}
        for i in range(comp.get_num_bones()):
            name = str(comp.get_bone_name(i))
            names.append(name)
            parent = str(comp.get_parent_bone(name))
            parents[name] = None if parent in ('None', '') else parent
            pose[name] = comp.get_socket_transform(name, unreal.RelativeTransformSpace.RTS_COMPONENT)
        return names, parents, pose
    finally:
        actor.destroy_actor()


def body_axes(pose):
    """forward, lateral (toward the right side), up in component space, from a reference pose."""
    up = _v(0, 0, 1)
    lat = pose['thigh_r'].translation - pose['thigh_l'].translation
    lat = unit(_v(lat.x, lat.y, 0))
    fwd = unit(cross(up, lat))
    if dot(pose['ball_l'].translation - pose['foot_l'].translation, fwd) < 0:
        fwd = scale(fwd, -1)
    return fwd, lat, up


# ---------- retarget pose ----------
def calibrate(rtg, source_mesh, target_mesh, spec, src_ref, tgt_ref):
    """Apply retarget_pose to a retargeter whose target pose already holds the installer's offsets (target ref
    local^-1 * Manny ref local). Returns what changed, bone by bone."""
    c = unreal.IKRetargeterController.get_controller(rtg)
    _, _, mpose = skeleton_info(source_mesh)
    _, _, hpose = skeleton_info(target_mesh)
    fwd, lat, up = body_axes(mpose)
    changed = {}
    if spec.get('clavicles') == 'own_rest':
        drop = float(spec.get('clavicle_drop', 0.0))
        for s in 'lr':
            cl, ua = f'clavicle_{s}', f'upperarm_{s}'
            offset = unreal.Quat(0, 0, 0, 1)
            if drop:      # lower the outer end about the axis across the bone and up, in its retarget-pose frame
                g = mpose['spine_05'].rotation * tgt_ref[cl]
                d = unit(hpose[cl].rotation.unrotate_vector(hpose[ua].translation - hpose[cl].translation))
                upl = unit(g.unrotate_vector(up))
                axis = unit(cross(d, upl))
                offset = deg_axis(axis, drop)
                if dot(offset.rotate_vector(d), upl) > dot(d, upl):
                    offset = deg_axis(axis, -drop)
            c.set_rotation_offset_for_retarget_pose_bone(cl, offset, TARGET)
            local_new = (tgt_ref[cl] * offset).inversed() * src_ref[cl] * src_ref[ua]
            c.set_rotation_offset_for_retarget_pose_bone(ua, tgt_ref[ua].inversed() * local_new, TARGET)
            changed[cl] = f'own rest, lowered {drop:.1f} deg' if drop else 'own rest'
            changed[ua] = "re-aimed: Manny's arm direction"
    for bone, degrees in (spec.get('pitch') or {}).items():
        g = mpose[bone].rotation
        axis = unit(g.unrotate_vector(lat))
        q = deg_axis(axis, degrees)
        d = mpose[NEXT[bone]].translation - mpose[bone].translation if bone in NEXT else unreal.Vector(0, 0, 10)
        moved = g.rotate_vector(q.rotate_vector(g.unrotate_vector(d)))
        if (dot(moved - d, fwd) > 0) != (degrees > 0):      # + bends forward
            q = deg_axis(axis, -degrees)
        c.set_rotation_offset_for_retarget_pose_bone(bone, c.get_rotation_offset_for_retarget_pose_bone(bone, TARGET) * q,
                                                     TARGET)
        changed[bone] = f'{degrees:+.1f} deg pitch (+ forward)'
    return changed


# ---------- gait style ----------
def _options(mesh):
    o = unreal.AnimPoseEvaluationOptions()
    o.optional_skeletal_mesh = mesh
    o.evaluation_type = unreal.AnimDataEvalType.RAW
    return o


def _sample(seq, mesh, times, names, space):
    o, out = _options(mesh), []
    for t in times:
        pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(seq, t, o)
        frame = {}
        for b in names:
            x = unreal.AnimPoseExtensions.get_bone_pose(pose, b, space)
            frame[b] = Xf(x.translation, x.rotation)
        out.append(frame)
    return out


def _num_keys(seq):
    try:
        n = unreal.AnimationLibrary.get_num_keys(seq)
        if n:
            return n
    except Exception:
        pass
    return unreal.AnimationLibrary.get_num_frames(seq) + 1


def _two_bone(hip, knee0, ankle0, hip0, target):
    a, b = length(knee0 - hip0), length(ankle0 - knee0)
    d_vec = target - hip
    d = min(max(length(d_vec), abs(a - b) + 1e-3), a + b - 1e-3)
    u = unit(d_vec)
    line = unit(ankle0 - hip0)
    side0 = (knee0 - hip0) - scale(line, dot(knee0 - hip0, line))
    side = side0 - scale(u, dot(side0, u))
    side = unit(side) if length(side) > 1e-6 else unit(cross(u, _v(0, 0, 1)))
    x = (a * a - b * b + d * d) / (2 * d)
    y = math.sqrt(max(a * a - x * x, 0.0))
    return hip + scale(u, x) + scale(side, y), hip + scale(u, d)


def style_clip(seq, mesh, skeleton, axes, ops, pins=PIN_DEFAULT, relaxed=None):
    """Rewrite one sequence's tracks with the gait operations. relaxed: finger bone -> local rotation of the
    character's relaxed hand (her idle), what finger_relax blends toward. Returns a receipt."""
    names, parents, _ = skeleton
    fwd, lat, up = axes
    n = _num_keys(seq)
    length_s = seq.get_play_length()
    times = [length_s * i / (n - 1) for i in range(n)]
    glob = _sample(seq, mesh, times, names, unreal.AnimPoseSpaces.WORLD)
    loc = _sample(seq, mesh, times, names, unreal.AnimPoseSpaces.LOCAL)
    root = 'root' if 'root' in names else None

    def side_shift(g):
        p = g['pelvis'].pos - (g[root].pos if root else _v(0, 0, 0))
        return dot(p, lat)

    mean_pel = mean_quat([g['pelvis'].rot for g in glob])
    mean_shift = sum(side_shift(g) for g in glob) / n
    k_roll, k_yaw, k_shift = ops.get('hip_roll', 1.0), ops.get('hip_yaw', 1.0), ops.get('hip_shift', 1.0)
    narrow, arm_in, upright = ops.get('narrow_cm', 0.0), ops.get('arm_in', 0.0), ops.get('upright', 0.0)
    elbow_bend = ops.get('elbow_bend', 1.0)
    finger_relax = ops.get('finger_relax', 0.0) if relaxed else 0.0
    fingers = set()
    if finger_relax:
        hands = {'hand_l', 'hand_r'}
        for b in names:      # parents come first: one pass collects everything under the hands
            if parents[b] in hands or parents[b] in fingers:
                fingers.add(b)
        fingers &= set(relaxed)
    pinned = {ik: src for src, ik in pins if ik in names and src in names}
    arm_rot = {}
    for s, out_dir in (('l', scale(lat, -1)), ('r', lat)):
        q = deg_axis(fwd, arm_in)
        arm_rot[s] = q if dot(q.rotate_vector(scale(up, -1)), out_dir) <= 0 else deg_axis(fwd, -arm_in)
    back = deg_axis(lat, upright)
    if dot(back.rotate_vector(up), fwd) > 0:
        back = deg_axis(lat, -upright)
    late = set()
    for b in names:      # pinned IK bones (and anything under them) are placed after the body
        if b in pinned or parents[b] in late:
            late.add(b)
    order = [b for b in names if b not in late] + [b for b in names if b in late]
    new_local = {b: [] for b in names}
    foot_err = 0.0
    # narrowing eases off on the foot that is in the air as it passes the planted one (swing_clear): a planted foot
    # keeps its full offset (no sliding), a passing foot swings around the standing leg instead of through its boot
    swing_clear = ops.get('swing_clear', 1.0)
    seps = [dot(g['foot_l'].pos - g['foot_r'].pos, fwd) for g in glob]
    sep_max = max(max(abs(s) for s in seps), 1e-3)

    def smooth(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)

    def narrow_weights(i):
        passing = 1.0 - smooth(abs(seps[i]) / sep_max / 0.6)
        lift = dot(glob[i]['foot_l'].pos - glob[i]['foot_r'].pos, up)
        # at the pass the foot in the air goes out by as much as the planted one came in (weight -1): easing it only
        # to its stock path left the gap short by the planted foot's own offset (Remora V17: 8.9 cm)
        return {'l': 1.0 - 2.0 * swing_clear * passing * smooth((lift - 0.5) / 2.0),
                'r': 1.0 - 2.0 * swing_clear * passing * smooth((-lift - 0.5) / 2.0)}

    for i in range(n):
        g0, l0 = glob[i], loc[i]
        weight = narrow_weights(i)
        ng = {}
        for b in order:
            p = parents[b]
            cur = l0[b] if p is None else ng[p].compose(l0[b])
            if b == 'pelvis':
                rv = rotvec(g0[b].rot * mean_pel.inversed())
                extra = scale(fwd, dot(rv, fwd) * (k_roll - 1)) + scale(up, dot(rv, up) * (k_yaw - 1))
                shift = (side_shift(g0) - mean_shift) * (k_shift - 1)
                cur = Xf(cur.pos + scale(lat, shift), from_rotvec(extra) * cur.rot)
            elif b == 'spine_01':
                cur = Xf(cur.pos, back * g0[b].rot)                       # chest held (upright tilts it back)
            elif b in ('upperarm_l', 'upperarm_r') and arm_in:
                cur = Xf(cur.pos, arm_rot[b[-1]] * cur.rot)
            elif b in ('lowerarm_l', 'lowerarm_r') and elbow_bend != 1.0:
                s = b[-1]      # scale the elbow's bend about its own hinge: < 1 opens it, lowering a high hand
                upper = cur.pos - ng[f'upperarm_{s}'].pos
                fore = cur.rot.rotate_vector(l0[f'hand_{s}'].pos)
                hinge = cross(upper, fore)
                if length(hinge) > 1e-6:
                    bend = math.atan2(length(hinge), dot(upper, fore))
                    cur = Xf(cur.pos, axis_angle(unit(hinge), (elbow_bend - 1.0) * bend) * cur.rot)
            elif b in ('thigh_l', 'thigh_r', 'calf_l', 'calf_r'):
                s = b[-1]
                target = g0[f'foot_{s}'].pos + scale(lat if s == 'l' else scale(lat, -1), narrow * weight[s])
                if b.startswith('thigh'):
                    knee, ankle = _two_bone(cur.pos, g0[f'calf_{s}'].pos, g0[f'foot_{s}'].pos, g0[b].pos, target)
                    foot_err = max(foot_err, length(ankle - target))
                    cur = Xf(cur.pos, from_to(g0[f'calf_{s}'].pos - g0[b].pos, knee - cur.pos) * g0[b].rot)
                else:
                    aim = cur.rot.rotate_vector(l0[f'foot_{s}'].pos)
                    cur = Xf(cur.pos, from_to(aim, target - cur.pos) * cur.rot)
            elif b in ('foot_l', 'foot_r'):
                cur = Xf(cur.pos, g0[b].rot)                               # soles kept
            elif b in fingers:      # toward her relaxed hand: Manny's splayed fingers read as claws on her
                step = scale(rotvec(l0[b].rot.inversed() * relaxed[b]), finger_relax)
                cur = Xf(cur.pos, ng[p].rot * (l0[b].rot * from_rotvec(step)))
            elif b in pinned:
                cur = ng[pinned[b]].compose(g0[pinned[b]].relative(g0[b]))
            ng[b] = cur
        for b in names:
            p = parents[b]
            new_local[b].append(ng[b] if p is None else ng[p].relative(ng[b]))
    changed = _write_tracks(seq, names, loc, new_local, 'RAC gait style')
    unreal.EditorAssetLibrary.set_metadata_tag(seq, 'RACGaitStyle', ','.join(f'{k}={v}' for k, v in sorted(ops.items())))
    unreal.EditorAssetLibrary.save_loaded_asset(seq, False)
    return {'keys': n, 'ops': ops, 'changed_bones': len(changed), 'max_foot_error_cm': round(foot_err, 3)}


def _write_tracks(seq, names, loc, new_local, label):
    """Write every bone whose local track changed; returns their names."""
    n = len(loc)
    changed = []
    ctrl = seq.controller
    ctrl.open_bracket(unreal.Text(label), False)
    try:
        for b in names:
            moved = any(length(new_local[b][i].pos - loc[i][b].pos) > 1e-3 or
                        abs(abs(new_local[b][i].rot.x * loc[i][b].rot.x + new_local[b][i].rot.y * loc[i][b].rot.y +
                                new_local[b][i].rot.z * loc[i][b].rot.z + new_local[b][i].rot.w * loc[i][b].rot.w) - 1) > 1e-7
                        for i in range(n))
            if moved:
                assert ctrl.set_bone_track_keys(b, [t.pos for t in new_local[b]], [t.rot for t in new_local[b]],
                                                [unreal.Vector(1, 1, 1)] * n, False), b
                changed.append(b)
    finally:
        ctrl.close_bracket(False)
    return changed


def _palm(frame, s):
    """The grip point of a hand: the centre of the fist, where a handle runs (the index, middle and ring fingers'
    first and second joints). A point at the knuckles left Remora's fist under the Sailwing's T-bar."""
    pts = [frame[b].pos for b in (f'index_01_{s}', f'middle_01_{s}', f'ring_01_{s}', f'index_02_{s}',
                                  f'middle_02_{s}', f'ring_02_{s}') if b in frame]
    if not pts:
        return frame[f'hand_{s}'].pos
    total = pts[0]
    for p in pts[1:]:
        total = total + p
    return scale(total, 1.0 / len(pts))


def fit_glider_grip(seq, mesh, skeleton, hero_seq, hero_mesh, back_socket, flight_offset, pins=PIN_DEFAULT):
    """The glider hangs from back_socket at flight_offset, placed for the hero's hands. First the glider is moved for
    this character (in the socket's frame, averaged over the clip and both hands) so its handles meet her palms in the
    pose she already has; then each hand is put on its handle: her palm where the hero's palm is relative to the
    glider at the same moment, with the hero's grip orientation (two-bone IK on the arm, elbow kept on its side), and
    the fingers take the hero's fist relative to the hand. Returns a receipt with the character's flight offset
    (translation, rotation) and any reach left over (cm)."""
    names, parents, _ = skeleton
    n = _num_keys(seq)
    length_s = seq.get_play_length()
    times = [length_s * i / (n - 1) for i in range(n)]
    hero_len = hero_seq.get_play_length()
    hero_names = [str(b) for b in skeleton_info(hero_mesh)[0]]
    glob = _sample(seq, mesh, times, names, unreal.AnimPoseSpaces.WORLD)
    loc = _sample(seq, mesh, times, names, unreal.AnimPoseSpaces.LOCAL)
    hero = _sample(hero_seq, hero_mesh, [min(t, hero_len) for t in times], hero_names, unreal.AnimPoseSpaces.WORLD)
    flight = Xf(flight_offset.translation, flight_offset.rotation)
    # move the glider to her hands: the mean miss between her palms and the hero's grip points, in the socket's frame
    shift = _v(0, 0, 0)
    for g0, h in zip(glob, hero):
        mount_her, mount_hero = g0[back_socket].compose(flight), h[back_socket].compose(flight)
        for s in 'lr':
            grip = mount_her.compose(mount_hero.relative(Xf(_palm(h, s), h[f'hand_{s}'].rot))).pos
            shift = shift + g0[back_socket].rot.unrotate_vector(_palm(g0, s) - grip)
    shift = scale(shift, 1.0 / (2 * n))
    flight = Xf(flight.pos + shift, flight.rot)
    fingers = {}
    for s in 'lr':
        under = {f'hand_{s}'}
        for b in names:      # parents come first, so one pass collects every descendant of the hand
            if parents[b] in under:
                under.add(b)
        fingers[s] = (under - {f'hand_{s}'}) & set(hero_names)
    pinned = {ik: src for src, ik in pins if ik in names and src in names}
    late = set()
    for b in names:
        if b in pinned or parents[b] in late:
            late.add(b)
    order = [b for b in names if b not in late] + [b for b in names if b in late]
    new_local = {b: [] for b in names}
    reach_left = {'l': 0.0, 'r': 0.0}
    for i in range(n):
        g0, l0, h = glob[i], loc[i], hero[i]
        mount_her = g0[back_socket].compose(flight)
        mount_hero = h[back_socket].compose(Xf(flight_offset.translation, flight_offset.rotation))
        target = {}
        for s in 'lr':      # her palm onto the hero's grip point, her hand turned as his
            rot = mount_her.rot * (mount_hero.rot.inversed() * h[f'hand_{s}'].rot)
            grip = mount_her.compose(mount_hero.relative(Xf(_palm(h, s), rot))).pos
            palm_in_hand = g0[f'hand_{s}'].relative(Xf(_palm(g0, s), g0[f'hand_{s}'].rot)).pos
            target[s] = Xf(grip - rot.rotate_vector(palm_in_hand), rot)
        ng = {}
        for b in order:
            p = parents[b]
            cur = l0[b] if p is None else ng[p].compose(l0[b])
            side = b[-1]
            if b in ('upperarm_l', 'upperarm_r'):
                elbow, wrist = _two_bone(cur.pos, g0[f'lowerarm_{side}'].pos, g0[f'hand_{side}'].pos, g0[b].pos,
                                         target[side].pos)
                reach_left[side] = max(reach_left[side], length(wrist - target[side].pos))
                cur = Xf(cur.pos, from_to(g0[f'lowerarm_{side}'].pos - g0[b].pos, elbow - cur.pos) * g0[b].rot)
            elif b in ('lowerarm_l', 'lowerarm_r'):
                aim = cur.rot.rotate_vector(l0[f'hand_{side}'].pos)
                cur = Xf(cur.pos, from_to(aim, target[side].pos - cur.pos) * cur.rot)
            elif b in ('hand_l', 'hand_r'):
                cur = Xf(cur.pos, target[side].rot)                        # the hero's grip on the handle
            elif side in 'lr' and b in fingers.get(side, ()):
                rel = h[f'hand_{side}'].rot.inversed() * h[b].rot          # the hero's fist, relative to the hand
                cur = Xf(cur.pos, ng[f'hand_{side}'].rot * rel)
            elif b in pinned:
                cur = ng[pinned[b]].compose(g0[pinned[b]].relative(g0[b]))
            ng[b] = cur
        for b in names:
            p = parents[b]
            new_local[b].append(ng[b] if p is None else ng[p].relative(ng[b]))
    changed = _write_tracks(seq, names, loc, new_local, 'RAC glider grip')
    unreal.EditorAssetLibrary.set_metadata_tag(seq, 'RACGliderGrip', hero_seq.get_path_name().split('.')[0])
    unreal.EditorAssetLibrary.save_loaded_asset(seq, False)
    return {'keys': n, 'hero_clip': hero_seq.get_path_name().split('.')[0], 'changed_bones': len(changed),
            'finger_bones': {s: len(fingers[s]) for s in 'lr'},
            'glider_moved_cm': [round(shift.x, 2), round(shift.y, 2), round(shift.z, 2)],
            'flight_offset': [flight.pos.x, flight.pos.y, flight.pos.z, flight.rot.x, flight.rot.y, flight.rot.z, flight.rot.w],
            'reach_left_cm': {s: round(v, 2) for s, v in reach_left.items()}}


def apply_gait_style(anim_dir, prefix, target_mesh, source_mesh, style):
    """Style every retargeted AnimSequence in anim_dir whose source name (without prefix) matches a pattern."""
    skeleton = skeleton_info(target_mesh)
    axes = body_axes(skeleton_info(source_mesh)[2])
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    report = {}
    relaxed = None
    idle = unreal.load_asset(f'{anim_dir}/{prefix}MM_Idle')
    if idle and any('finger_relax' in ops for ops in style.values()):
        frame = _sample(idle, target_mesh, [min(1.0, idle.get_play_length())], skeleton[0], unreal.AnimPoseSpaces.LOCAL)[0]
        relaxed = {b: x.rot for b, x in frame.items()}
    for data in sorted(registry.get_assets_by_path(anim_dir), key=lambda d: str(d.asset_name)):
        if str(data.asset_class_path.asset_name) != 'AnimSequence':
            continue
        name = str(data.asset_name)
        source_name = name[len(prefix):] if name.startswith(prefix) else name
        pattern = next((p for p in style if fnmatch.fnmatchcase(source_name, p)), None)
        if pattern:
            report[name] = {'pattern': pattern, **style_clip(data.get_asset(), target_mesh, skeleton, axes, style[pattern],
                                                             relaxed=relaxed)}
    return report
