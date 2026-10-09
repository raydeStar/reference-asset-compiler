"""Coat-tail chains on a synthetic body: the profile block, and (with RAC_BLENDER) the real stage.

The Blender checks build a Manny-named lower body (pelvis, spine_01, thighs,
calves, feet, balls) wearing trouser legs, a torso and an open-hemmed skirt
that flares from the belt to the knee, all one skinned mesh like a scanned
outfit. add_coat_chains.py must hang four chains on the skirt, skin the skirt
to them and leave the legs and torso exactly as they were. Variants: a skirt
that ends above the knee, and one with a vent where a chain hangs.
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from coat_profile import DEFAULTS, bone_names, resolve_coat  # noqa: E402

BLENDER = os.environ.get("RAC_BLENDER")
needs_blender = pytest.mark.skipif(not BLENDER, reason="Set RAC_BLENDER for real Blender checks")

# --- the profile block, no Blender --------------------------------------------------------------


def test_no_block_means_no_coat():
    assert resolve_coat(None) is None


def test_an_empty_block_is_four_chains_of_three():
    coat = resolve_coat({})
    assert coat["chains"] == {"front_l": 25.0, "front_r": -25.0, "back_l": 150.0, "back_r": -150.0}
    assert coat["bones_per_chain"] == 3 and coat["top_below_pelvis_m"] == 0.04
    assert coat["hem_z_m"] is None and coat["hem_above_knee_m"] == 0.0 and not coat["open_front"]


def test_chain_names_follow_mannys_index_then_side_pattern():
    assert bone_names("front_l", 3) == ["coat_front_01_l", "coat_front_02_l", "coat_front_03_l", "coat_front_end_l"]
    assert bone_names("side_r", 2) == ["coat_side_01_r", "coat_side_02_r", "coat_side_end_r"]


@pytest.mark.parametrize("block, message", [
    ({"chains": {"front": 20}}, "front"),
    ({"chains": {"end_l": 20}}, "end_l"),
    ({"chains": {"front_l": 200}}, "180"),
    ({"chains": {"a_l": 180, "a_r": -180}}, "share an angle"),
    ({"chains": {}}, "at least one chain"),
    ({"hem_z_m": 0.5, "hem_above_knee_m": 0.0}, "not both"),
    ({"bones_per_chain": 0}, "bones_per_chain"),
    ({"leg_clearance": 0.1}, "Unknown coat keys"),
    ([25, -25], "object"),
])
def test_a_bad_block_stops_before_a_build(block, message):
    with pytest.raises(ValueError, match=message):
        resolve_coat(block)


def test_comment_keys_are_allowed():
    assert resolve_coat({"_comment": "knee-length coat", "_chains": "x"})["chains"] == DEFAULTS["chains"]


# --- the stage on a synthetic body (Blender) -------------------------------------------------------

PELVIS_Z, KNEE_Z, TOP_Z = 1.0, 0.52, 0.96
SKIRT = dict(top=0.97, bottom=0.50, r_top=0.19, r_bottom=0.30, segs=32, rings=12, vent=None)

MAKE = r'''
import math, sys, bpy
out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
arm_data = bpy.data.armatures.new("root")
arm = bpy.data.objects.new("root", arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
def bone(name, head, parent=None):
    b = arm_data.edit_bones.new(name)
    b.head = head
    b.tail = (head[0], head[1] + 0.08, head[2])   # Manny-style +Y stubs
    b.parent = arm_data.edit_bones[parent] if parent else None
bone("pelvis", (0, 0, 1.0))
bone("spine_01", (0, 0, 1.1), "pelvis")
for side, sx in (("l", 1), ("r", -1)):
    bone("thigh_" + side, (0.1 * sx, 0, 0.95), "pelvis")
    bone("calf_" + side, (0.1 * sx, 0, 0.52), "thigh_" + side)
    bone("foot_" + side, (0.1 * sx, 0, 0.08), "calf_" + side)
    bone("ball_" + side, (0.1 * sx, -0.12, 0.02), "foot_" + side)
bpy.ops.object.mode_set(mode="OBJECT")

verts, faces, weights = [], [], []
def tube(cx, cy, r_top, r_bottom, z_top, z_bottom, segs, rings, weigh, vent=None):
    base = len(verts)
    for i in range(rings + 1):
        t = i / rings
        z, r = z_top + (z_bottom - z_top) * t, r_top + (r_bottom - r_top) * t
        for s in range(segs):
            a = 2 * math.pi * s / segs                   # 0 = front (-Y), toward +X
            x, y = cx + r * math.sin(a), cy - r * math.cos(a)
            verts.append((x, y, z))
            weights.append(weigh(x, y, z))
    for i in range(rings):
        for s in range(segs):
            a, b = base + i * segs + s, base + i * segs + (s + 1) % segs
            if vent:   # a slit up from the hem: (degrees it is centred on, half width, top height)
                mid = math.degrees(2 * math.pi * (s + 0.5) / segs)
                if abs((mid - vent[0] + 180) % 360 - 180) < vent[1] and verts[a][2] < vent[2]:
                    continue
            faces.append((a, b, b + segs, a + segs))
tube(0, 0, 0.16, 0.16, 1.25, 0.98, 24, 6, lambda x, y, z: {"pelvis": 0.5, "spine_01": 0.5})
for side, sx in (("l", 1), ("r", -1)):
    tube(0.1 * sx, 0, 0.07, 0.07, 0.95, 0.10, 16, 17,
         lambda x, y, z, side=side: {"thigh_" + side: 0.9, "pelvis": 0.1} if z >= 0.52
         else {"calf_" + side: 0.75, "thigh_" + side: 0.25})
S = SKIRT
tube(0, 0, S["r_top"], S["r_bottom"], S["top"], S["bottom"], S["segs"], S["rings"],
     lambda x, y, z: {"pelvis": 0.6, ("thigh_l" if x > 1e-6 else "thigh_r"): 0.4} if abs(x) > 1e-6 else {"pelvis": 1.0},
     S["vent"])
me = bpy.data.meshes.new("Synth_Outfit")
me.from_pydata(verts, [], faces)
obj = bpy.data.objects.new("Synth_Outfit", me)
bpy.context.scene.collection.objects.link(obj)
obj.parent = arm
for i, w in enumerate(weights):
    for name, value in w.items():
        group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
        group.add([i], value, "REPLACE")
obj.modifiers.new("Armature", "ARMATURE").object = arm
bpy.ops.wm.save_as_mainfile(filepath=out)
'''.replace("S = SKIRT", "S = " + repr(SKIRT))

DUMP = r'''
import json, sys, bpy
args = sys.argv[sys.argv.index("--") + 1:]
src, out = args
if src.endswith(".fbx"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=src)
else:
    bpy.ops.wm.open_mainfile(filepath=src)
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
bones = {}
for b in arm.data.bones:
    m = b.matrix_local
    bones[b.name] = {"parent": b.parent.name if b.parent else None, "deform": b.use_deform,
                     "head": list(b.head_local), "x": list(m.col[0][:3]), "z": list(m.col[2][:3]),
                     "children": [c.name for c in b.children]}
mesh = max((o for o in bpy.context.scene.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
names = [g.name for g in mesh.vertex_groups]
verts = [{"co": list(mesh.matrix_world @ v.co), "w": {names[g.group]: g.weight for g in v.groups if g.weight > 0}}
         for v in mesh.data.vertices]
json.dump({"bones": bones, "verts": verts}, open(out, "w"))
'''


def blender(*args):
    result = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", *map(str, args)],
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    return result


def dump(tmp_path, source, name):
    script = tmp_path / "dump.py"
    script.write_text(DUMP)
    blender("--python", script, "--", source, tmp_path / name)
    return json.loads((tmp_path / name).read_text())


def coat_run(tmp_path, block, skirt=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    make = tmp_path / "make.py"
    make.write_text(MAKE if skirt is None else MAKE.replace("S = " + repr(SKIRT), "S = " + repr({**SKIRT, **skirt})))
    source = tmp_path / "Synth_UE5.blend"
    blender("--python", make, "--", source)
    profile = tmp_path / "synth.json"
    profile.write_text(json.dumps({"name": "Synth", "coat": block}))
    fbx, coated = tmp_path / "export/Synth_UE5.fbx", tmp_path / "coated.blend"
    run = blender(source, "--python", ROOT / "scripts/blender/add_coat_chains.py", "--", fbx,
                  "--profile", profile, "--save-blend", coated)
    receipt = json.loads((tmp_path / "export/Synth_UE5.coat.json").read_text())
    return source, coated, fbx, receipt, run


@pytest.fixture(scope="module")
def coated(tmp_path_factory):
    if not BLENDER:
        pytest.skip("Set RAC_BLENDER for real Blender checks")
    tmp = tmp_path_factory.mktemp("coat")
    source, blend, fbx, receipt, _ = coat_run(tmp, {"leg_clearance_m": 0.12})
    return {"before": dump(tmp, source, "before.json"), "after": dump(tmp, blend, "after.json"),
            "fbx": dump(tmp, fbx, "fbx.json"), "receipt": receipt, "fbx_path": fbx}


CHAINS = {"front_l": 25, "front_r": -25, "back_l": 150, "back_r": -150}


def azimuth(co):
    return math.degrees(math.atan2(co[0], -co[1]))


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


@needs_blender
def test_chains_hang_from_the_pelvis_with_x_down_the_chain_and_z_outward(coated):
    bones = coated["after"]["bones"]
    for chain, degrees in CHAINS.items():
        names = bone_names(chain, 3)
        assert [bones[n]["parent"] for n in names] == ["pelvis", *names[:-1]]
        assert [bones[n]["deform"] for n in names] == [True, True, True, False]
        a = math.radians(degrees)
        radial = [math.sin(a), -math.cos(a), 0.0]
        for parent, child in zip(names, names[1:]):
            down = unit([c - p for c, p in zip(bones[child]["head"], bones[parent]["head"])])
            assert dot(bones[parent]["x"], down) > 0.9999, parent
            assert down[2] < -0.9, parent                      # hangs down
            assert dot(bones[parent]["z"], radial) > 0.95, parent
        assert dot(bones[names[-1]]["x"], bones[names[-2]]["x"]) > 0.9999
        # On the skirt: the root just under the belt, the leaf at the knee.
        root, leaf = bones[names[0]]["head"], bones[names[-1]]["head"]
        assert root[2] == pytest.approx(TOP_Z, abs=1e-4) and leaf[2] == pytest.approx(KNEE_Z, abs=1e-4)
        assert math.hypot(*root[:2]) == pytest.approx(0.1923, abs=0.004)
        assert math.hypot(*leaf[:2]) == pytest.approx(0.2953, abs=0.004)
        assert azimuth(root) == pytest.approx(degrees, abs=0.01)
    assert coated["receipt"]["segment_m"] == pytest.approx((TOP_Z - KNEE_Z) / 3, abs=1e-4)


@needs_blender
def test_the_fbx_carries_the_chains(coated):
    bones = coated["fbx"]["bones"]
    for chain in CHAINS:
        names = bone_names(chain, 3)
        assert [bones[n]["parent"] for n in names] == ["pelvis", *names[:-1]]
    assert coated["fbx_path"].with_suffix(".json").is_file()   # export_ue5_character.py's provenance


def split(coated):
    """Vertex indices of the legs and torso, and of the skirt (the fixture's build order)."""
    torso, leg = 24 * 7, 16 * 18
    first_skirt = torso + 2 * leg
    return list(range(first_skirt)), list(range(first_skirt, len(coated["after"]["verts"])))


@needs_blender
def test_legs_and_torso_keep_their_weights_exactly(coated):
    body, _ = split(coated)
    before, after = coated["before"]["verts"], coated["after"]["verts"]
    assert [before[i]["w"] for i in body] == [after[i]["w"] for i in body]


@needs_blender
def test_the_skirt_weights_are_whole_and_within_four_influences(coated):
    _, skirt = split(coated)
    after = coated["after"]["verts"]
    for i in skirt:
        w = after[i]["w"]
        assert 1 <= len(w) <= 4
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-5)
    receipt = coated["receipt"]
    assert receipt["coat_zero_weight_vertices"] == 0 and receipt["coat_max_influences"] <= 4
    assert 0 < receipt["coat_vertices"] <= len(skirt)
    assert set(receipt["chains"]) == set(CHAINS)
    # No ring vertex sits exactly on a chain's angle (32 segments), so just under 1.
    assert all(0.95 < c["max_weight"] <= 1.0 and c["hem_found"] for c in receipt["chains"].values())


@needs_blender
def test_the_belt_rides_the_pelvis_and_the_skirt_below_rides_the_chains(coated):
    _, skirt = split(coated)
    before, after = coated["before"]["verts"], coated["after"]["verts"]
    segment = (TOP_Z - KNEE_Z) / 3
    for i in skirt:
        x, y, z = after[i]["co"]
        leg = math.hypot(abs(x) - 0.1, y)          # from the nearer thigh/calf axis (vertical here)
        chain_share = sum(w for name, w in after[i]["w"].items() if name.startswith("coat_"))
        if z >= TOP_Z or leg <= 0.12:              # above the roots, or hugging a leg: untouched
            assert after[i]["w"] == before[i]["w"]
        elif z <= TOP_Z - segment - 1e-3 and leg >= 0.15:
            assert chain_share == pytest.approx(1.0, abs=1e-6), after[i]
    # Down the coat the share only grows.
    rows = sorted({round(after[i]["co"][2], 5) for i in skirt}, reverse=True)
    shares = [max(sum(w for n, w in after[i]["w"].items() if n.startswith("coat_"))
                  for i in skirt if round(after[i]["co"][2], 5) == z) for z in rows]
    assert all(b >= a - 1e-6 for a, b in zip(shares, shares[1:])), shares


@needs_blender
def test_weights_fall_off_smoothly_between_neighbouring_chains(coated):
    _, skirt = split(coated)
    after = coated["after"]["verts"]
    z = min({round(after[i]["co"][2], 5) for i in skirt}, key=lambda h: abs(h - 0.61))
    ring = sorted((i for i in skirt if round(after[i]["co"][2], 5) == z), key=lambda i: azimuth(after[i]["co"]))
    assert len(ring) == SKIRT["segs"]
    for chain, degrees in CHAINS.items():
        bones = bone_names(chain, 3)[:3]
        share = [sum(after[i]["w"].get(b, 0.0) for b in bones) for i in ring]
        angles = [azimuth(after[i]["co"]) for i in ring]
        # 11.25 degree steps across a 50 degree smoothstep: at most 1.5 * 11.25 / 50 = 0.34 apart.
        jumps = [abs(a - b) for a, b in zip(share, share[1:] + share[:1])]
        assert max(jumps) < 0.35, (chain, share)
        nearest = min(range(len(ring)), key=lambda k: abs((angles[k] - degrees + 180) % 360 - 180))
        assert share[nearest] > 0.9, (chain, share)
        for step in (1, -1):                       # falling away on both sides, never rising again
            run = [share[(nearest + step * k) % len(ring)] for k in range(len(ring) // 2)]
            assert all(b <= a + 1e-9 for a, b in zip(run, run[1:])), (chain, step, run)
        # Nothing reaches past the neighbouring chains: front_l stops at front_r and back_l.
        arcs = sorted((other - degrees) % 360 for name, other in CHAINS.items() if name != chain)
        to_next, to_previous = arcs[0], 360 - arcs[-1]
        for angle, value in zip(angles, share):
            off = (angle - degrees + 180) % 360 - 180
            if off >= to_next or -off >= to_previous:
                assert value == 0.0, (chain, angle, value)


@needs_blender
def test_an_open_front_never_blends_across_the_opening(tmp_path):
    _, blend, _, receipt, _ = coat_run(tmp_path, {"open_front": True})
    after = dump(tmp_path, blend, "after.json")["verts"]
    assert receipt["coat"]["open_front"] is True
    for v in after:
        a, w = azimuth(v["co"]), v["w"]
        if v["co"][2] < TOP_Z and 1.0 < a < 25.0:
            assert not any(n.startswith("coat_front") and n.endswith("_r") for n in w), v
        if v["co"][2] < TOP_Z and -25.0 < a < -1.0:
            assert not any(n.startswith("coat_front") and n.endswith("_l") for n in w), v


@needs_blender
def test_a_coat_that_ends_above_the_knee_finds_its_hem_where_the_profile_says(tmp_path):
    # The skirt stops 10 cm above the knee: at the knee the rays only meet trouser legs.
    bottom = KNEE_Z + 0.10
    skirt = {"bottom": bottom, "r_bottom": 0.27}
    _, _, _, missed, run = coat_run(tmp_path / "at-knee", {}, skirt)
    assert not any(c["hem_found"] for c in missed["chains"].values())
    assert "COAT WARNING" in run.stdout
    for c in missed["chains"].values():       # the receipt says where the coat ends instead
        assert c["coat_bottom_z_m"] == pytest.approx(bottom, abs=0.01)
    _, blend, _, receipt, _ = coat_run(tmp_path / "above-knee", {"hem_above_knee_m": 0.08}, skirt)
    bones = dump(tmp_path / "above-knee", blend, "after.json")["bones"]
    r_at = 0.19 + (0.27 - 0.19) * (0.97 - (KNEE_Z + 0.08)) / (0.97 - bottom)   # the skirt there, if it went on
    for chain, c in receipt["chains"].items():
        assert c["hem_found"], chain
        assert c["hem_ray_z_m"] == pytest.approx(KNEE_Z + 0.105, abs=1e-4)     # 2.5 cm up: the skirt's last ring
        leaf = bones[bone_names(chain, 3)[-1]]["head"]
        assert leaf[2] == pytest.approx(KNEE_Z + 0.08, abs=1e-4)
        assert math.hypot(*leaf[:2]) == pytest.approx(0.27, abs=0.006) and math.hypot(*leaf[:2]) < r_at + 0.006


@needs_blender
def test_a_hem_ray_that_slips_through_a_vent_finds_the_coat_beside_it(tmp_path):
    # A 4-degree-wide slit up the back at back_l's angle, from the hem to above the knee rays.
    _, _, _, receipt, _ = coat_run(tmp_path, {}, {"vent": [150.0, 2.0, 0.7]})
    back = receipt["chains"]["back_l"]
    assert back["hem_found"] and back["hem_ray_deg"] != 150.0 and abs(back["hem_ray_deg"] - 150.0) <= 6.0
    assert back["radius_hem_m"] == pytest.approx(0.2953, abs=0.006)
    assert all(c["hem_found"] for c in receipt["chains"].values())
    assert receipt["chains"]["front_l"]["hem_ray_deg"] == 25.0
