"""rig_ue5_character.py --plan-ignore: the joint plan leaves the named objects (mesh hair) out of its measurements.

Every stage is stubbed; what matters is the plan command it issues.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rig_ue5_character  # noqa: E402


def plan_command(tmp_path, monkeypatch, *options):
    issued = []

    def run(cmd, log):
        cmd = [str(c) for c in cmd]
        issued.append(cmd)
        if any(c.endswith("fit_ue5_manny_rig.py") for c in cmd):
            fit = Path(cmd[cmd.index("--out") + 1])
            fit.mkdir(parents=True)
            (fit / "fit-report.json").write_text(json.dumps(
                {"bone_count": 89, "deform_bones": 80, "outputs": {"export_blend": str(fit / "x.blend")}}))
        elif any(c.endswith("pose_ue5_anim_test.py") for c in cmd):
            poses = Path(cmd[cmd.index("--") + 3])
            poses.mkdir(parents=True)
            (poses / "pose-receipts.json").write_text("[]")
        elif any(c.endswith("plan_ue5_joints.py") for c in cmd):
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps({"derivation": {}}))

    monkeypatch.setattr(rig_ue5_character, "run", run)
    monkeypatch.setattr(sys, "argv", ["rig_ue5_character.py", str(tmp_path / "c.blend"), str(tmp_path / "out"),
                                      "--manny-dir", str(tmp_path), "--blender", "blender", *options])
    rig_ue5_character.main()
    plan = next(c for c in issued if any(x.endswith("plan_ue5_joints.py") for x in c))
    return plan[plan.index("--") + 1:]


def test_the_plan_ignores_what_it_is_told_to(tmp_path, monkeypatch):
    plan = plan_command(tmp_path, monkeypatch, "--name", "Hero", "--plan-ignore", "Hero_hair")
    assert plan[plan.index("--ignore"):plan.index("--ignore") + 2] == ["--ignore", "Hero_hair"]


def test_by_default_the_plan_measures_every_mesh(tmp_path, monkeypatch):
    assert "--ignore" not in plan_command(tmp_path, monkeypatch, "--name", "Hero")
