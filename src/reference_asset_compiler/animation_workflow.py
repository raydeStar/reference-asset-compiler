"""Hash-bound animation recipes, isolated derivatives and honest review receipts."""
from __future__ import annotations

import math
import shutil
import time
import platform
from importlib.metadata import version
from datetime import datetime, timezone
from pathlib import Path

from .animation_motion import derive_packet, measure_packet, validate_packet
from .io import read_json, sha256_file, write_retained_json

SCHEMA = "reference-asset-compiler.animation-recipe.v1"
OPEN_CODE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "PSF-2.0",
             "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later", "AGPL-3.0-only",
             "AGPL-3.0-or-later", "LGPL-2.1-or-later", "LGPL-3.0-or-later"}
OPEN_DATA = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0"}


def toolchain():
    return {'python': platform.python_version(),
            'numpy': version('numpy'), 'scipy': version('scipy'),
            'workflow': binding(__file__),
            'motion': binding(Path(__file__).with_name('animation_motion.py'))}


def binding(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha256_file(path)}


def bound_path(record, base):
    if not isinstance(record, dict) or not isinstance(record.get("path"), str):
        raise ValueError("expected a path/sha256 binding")
    path = Path(record["path"])
    path = (base / path).resolve() if not path.is_absolute() else path.resolve()
    if sha256_file(path) != record.get("sha256"):
        raise ValueError(f"hash mismatch: {path}")
    return path


def load_recipe(path):
    path = Path(path).resolve()
    recipe = read_json(path)
    if recipe.get("schema") != SCHEMA:
        raise ValueError("unsupported animation recipe schema")
    if not isinstance(recipe.get("pose_intent"), str) or not recipe["pose_intent"].strip():
        raise ValueError("state the intended stance/performance")
    source = bound_path(recipe["packet"], path.parent)
    character = bound_path(recipe["character"], path.parent)
    if recipe.get('configuration'):
        bound_path(recipe['configuration'], path.parent)
    packet = validate_packet(read_json(source))
    if packet.get("provenance", {}).get("character_blend_sha256") != sha256_file(character):
        raise ValueError("packet is not bound to this character authority")
    if recipe.get("coordinates") != {"units": "cm", "up": "Z", "rotation": "xyzw", "space": "UE-local"}:
        raise ValueError("explicit UE-local/cm/Z/xyzw coordinate contract required")
    provider = recipe.get("provider", {})
    if provider.get("kind") not in {"licensed-library", "capture", "generator"}:
        raise ValueError("unknown motion provider")
    components = provider.get("components", [])
    if not components:
        raise ValueError("provider has no license evidence")
    roles = set()
    for item in components:
        role = item.get("role")
        roles.add(role)
        allowed = OPEN_CODE if role == "code" else OPEN_DATA if role in {"motion", "training-data"} else OPEN_CODE | OPEN_DATA
        if role not in {"code", "motion", "weights", "body-model", "training-data", "dependency"} or item.get("license") not in allowed:
            raise ValueError(f"component not admitted by strict-open policy: {item.get('name')}")
        bound_path(item["artifact"], path.parent)
        bound_path(item["license_evidence"], path.parent)
    required = {"code", "weights", "training-data"} if provider["kind"] == "generator" else {"motion", "code"}
    if not required <= roles or provider.get("dependencies_complete") is not True:
        raise ValueError("incomplete provider dependency/license inventory")
    for item in recipe.get("mapping", []):
        bound_path(item, path.parent)
    skeleton = read_json(bound_path(recipe["skeleton"], path.parent)) if recipe.get("skeleton") else None
    if skeleton and skeleton.get("source_sha256") != sha256_file(character):
        raise ValueError("skeleton inspection belongs to another character")
    return recipe, packet, skeleton


def preflight(path):
    recipe, packet, skeleton = load_recipe(path)
    return {"schema": "reference-asset-compiler.animation-preflight.v1", "ok": True,
            "recipe": binding(path), "clip_count": len(packet["clips"]),
            "provider": recipe["provider"]["kind"], "skeleton_available": skeleton is not None,
            "human_approved": False, "production_ready": False,
            "note": "License declarations and retained file hashes checked; no artistic verdict."}


def derive(path, output):
    recipe, packet, skeleton = load_recipe(path)
    output = Path(output).resolve()
    # Validate all edits in memory before making a new output directory.
    started = time.monotonic()
    candidate = derive_packet(packet, recipe.get("operations", []), skeleton)
    output.mkdir(parents=True, exist_ok=False)
    target = output / "clips.json"
    candidate.setdefault("provenance", {})["animation_workflow"] = {
        "input": binding(Path(path).parent / recipe["packet"]["path"]),
        "recipe": binding(path), "operations": recipe.get("operations", []),
        "human_approved": False}
    write_retained_json(target, candidate)
    receipt = {"schema": "reference-asset-compiler.animation-derivative.v1",
               "toolchain": toolchain(),
               "recipe": binding(path), "input": recipe["packet"], "output": binding(target),
               "elapsed_seconds": time.monotonic() - started, "operations": recipe.get("operations", []),
               "human_approved": False, "production_ready": False}
    write_retained_json(output / "receipt.json", receipt)
    return receipt


def measure(path, output, candidate=None):
    recipe, packet, skeleton = load_recipe(path)
    if skeleton is None:
        raise ValueError("inspect the character in Blender before measuring motion")
    source = bound_path(recipe["packet"], Path(path).resolve().parent)
    if candidate:
        source = Path(candidate).resolve()
        packet = read_json(source)
        if packet.get("provenance", {}).get("character_blend_sha256") != recipe["character"]["sha256"]:
            raise ValueError("candidate belongs to a different character")
    report = measure_packet(packet, skeleton, recipe["benchmark"])
    report.update(schema="reference-asset-compiler.animation-measurements.v1", packet=binding(source),
                  toolchain=toolchain(),
                  recipe=binding(path), skeleton=recipe["skeleton"],
                  benchmark=recipe["benchmark"], production_ready=False)
    write_retained_json(Path(output), report)
    return report


def compare(baseline, candidate, output):
    a, b = read_json(Path(baseline)), read_json(Path(candidate))
    if a.get("schema") != "reference-asset-compiler.animation-measurements.v1" or a.get("schema") != b.get("schema"):
        raise ValueError("comparison needs measurement receipts")
    for report, parent in ((a, Path(baseline).parent), (b, Path(candidate).parent)):
        bound_path(report["packet"], parent)
        bound_path(report["recipe"], parent)
        bound_path(report["skeleton"], Path(report["recipe"]["path"]).parent)
    if a["skeleton"]["sha256"] != b["skeleton"]["sha256"] or a["benchmark"] != b["benchmark"]:
        raise ValueError("compare the same skeleton and benchmark conditions")
    if set(a["clips"]) != set(b["clips"]):
        raise ValueError("comparison clip coverage differs")
    deltas = {}
    for name in a["clips"]:
        deltas[name] = {k: b["clips"][name][k] - a["clips"][name][k]
                        for k in ("loop_position_gap_cm", "loop_angle_gap_deg", "peak_joint_speed_cm_s")
                        if a["clips"][name][k] is not None and b["clips"][name][k] is not None}
        deltas[name]["contact_drift_cm"] = [cb["drift_cm"] - ca["drift_cm"] for ca, cb in
                                           zip(a["clips"][name]["contacts"], b["clips"][name]["contacts"], strict=True)]
        deltas[name]['contact_penetration_cm'] = [cb['penetration_cm'] - ca['penetration_cm']
            if ca['penetration_cm'] is not None and cb['penetration_cm'] is not None else None
            for ca, cb in zip(a['clips'][name]['contacts'], b['clips'][name]['contacts'], strict=True)]
    transition_deltas = []
    for ta, tb in zip(a['transitions'], b['transitions'], strict=True):
        if any(ta[k] != tb[k] for k in ('from', 'to', 'from_s', 'to_s')):
            raise ValueError('transition sampling conditions differ')
        transition_deltas.append({'from': ta['from'], 'to': ta['to'],
                                  **{k: tb[k] - ta[k] for k in ('position_gap_cm', 'velocity_gap_cm_s')}})
    result = {"schema": "reference-asset-compiler.animation-comparison.v1", "baseline": binding(baseline),
              "candidate": binding(candidate), "deltas_candidate_minus_baseline": deltas,
              "transition_deltas_candidate_minus_baseline": transition_deltas,
              "winner": None, "human_approved": False, "production_ready": False,
              "note": "Negative error deltas may help; reduced movement alone is not improved acting."}
    write_retained_json(Path(output), result)
    return result


def compare_models(baseline, candidate, output):
    from .animation_export import model_payload_fingerprint
    a = model_payload_fingerprint(Path(baseline).read_bytes())
    b = model_payload_fingerprint(Path(candidate).read_bytes())
    result = {'baseline': binding(baseline), 'candidate': binding(candidate),
              'baseline_model_fingerprint': a, 'candidate_model_fingerprint': b,
              'model_preserved': a == b, 'human_approved': False,
              'scope': 'Embedded GLB geometry, UVs, indices, weights, morphs, materials, images, nodes and skin bind data; excludes animation payload.'}
    write_retained_json(Path(output), result)
    if a != b:
        raise ValueError('exported model payload changed; retained comparison receipt')
    return result


def record_review(packet, status, reviewer, note, evidence, cleanup_minutes, output, clips=None):
    from .contracts import AUTOMATION_REVIEWERS
    if status not in {"accepted", "rejected", "pending"}:
        raise ValueError("unknown review status")
    if status != "pending" and (not reviewer.strip() or reviewer.strip().lower() in AUTOMATION_REVIEWERS):
        raise ValueError("artistic acceptance/rejection needs the actual human reviewer")
    if not note.strip() or not math.isfinite(cleanup_minutes) or cleanup_minutes < 0:
        raise ValueError("review needs a note and nonnegative cleanup minutes")
    if status != "pending" and not evidence:
        raise ValueError("human review needs retained evidence")
    data = validate_packet(read_json(Path(packet)))
    clips = list(data['clips']) if clips is None else clips
    if not clips or len(set(clips)) != len(clips) or set(clips) - set(data['clips']):
        raise ValueError('review must identify unique existing clips')
    result = {"schema": "reference-asset-compiler.animation-review.v1", "packet": binding(packet),
              "status": status, "reviewer": reviewer, "note": note,
              "evidence": [binding(p) for p in evidence], "cleanup_minutes": cleanup_minutes,
              "clips": clips,
              "recorded_at": datetime.now(timezone.utc).isoformat(), "production_ready": False}
    write_retained_json(Path(output), result)
    return result


def review_summary(paths):
    rows, seen = [], set()
    for path in paths:
        row = read_json(Path(path))
        if row.get("schema") != "reference-asset-compiler.animation-review.v1":
            raise ValueError("expected animation review receipt")
        bound_path(row["packet"], Path(path).parent)
        for item in row["evidence"]:
            bound_path(item, Path(path).parent)
        for clip in row['clips']:
            key = (row["packet"]["sha256"], clip)
            if key in seen:
                raise ValueError("select one review per packet/clip; do not double count revisions")
            seen.add(key)
        rows.append(row)
    decided = [r for r in rows if r["status"] in {"accepted", "rejected"}]
    accepted = [r for r in decided if r["status"] == "accepted"]
    minutes = sum(r["cleanup_minutes"] for r in rows)
    decided_clips = sum(len(r['clips']) for r in decided)
    accepted_clips = sum(len(r['clips']) for r in accepted)
    return {"reviewed": len(decided), "accepted": len(accepted), "pending": len(rows)-len(decided),
            "reviewed_clips": decided_clips, "accepted_clips": accepted_clips,
            "acceptance_rate": accepted_clips/decided_clips if decided_clips else None,
            "cleanup_minutes": minutes, "minutes_per_accepted_clip": minutes/accepted_clips if accepted_clips else None,
            "scope": "Selected packet revisions and named clips; include rejected-attempt cleanup time."}


def package(path, files, output):
    recipe, _, _ = load_recipe(path)
    output = Path(output).resolve()
    if not files:
        raise ValueError("package needs explicit export/evidence files")
    inputs = [Path(f).resolve() for f in files]
    if len({p.name for p in inputs}) != len(inputs):
        raise ValueError("package file names must be unique")
    if any(p.name in {'manifest.json', 'recipe.json'} or p.name.startswith('license-') for p in inputs):
        raise ValueError('reserved package file name')
    records = [binding(p) for p in inputs]
    output.mkdir(parents=True, exist_ok=False)
    for source in inputs:
        shutil.copy2(source, output / source.name)
    shutil.copy2(path, output / 'recipe.json')
    # Evidence is included, not just URLs that may later disappear.
    licenses = []
    for i, component in enumerate(recipe["provider"]["components"]):
        src = bound_path(component["license_evidence"], Path(path).resolve().parent)
        shutil.copy2(src, output / f"license-{i}{src.suffix}")
        licenses.append({'component': component['name'], 'license': component['license'],
                         'evidence': binding(output / f'license-{i}{src.suffix}')})
    result = {"schema": "reference-asset-compiler.animation-package.v1", "recipe": binding(path),
              "inputs": records, "files": [binding(output / p.name) for p in inputs],
              "licenses": licenses,
              "human_approved": False, "production_ready": False}
    write_retained_json(output / "manifest.json", result)
    return result


def add_cli(subcommands):
    parser = subcommands.add_parser("animation", help="Open animation recipes, edits, measurements and reviews")
    commands = parser.add_subparsers(dest="animation_command", required=True)
    p = commands.add_parser('init', help='Bind a reusable profile to explicitly supplied source files')
    p.add_argument('profile', type=Path)
    p.add_argument('--input', action='append', default=[], metavar='NAME=PATH')
    p.add_argument('--output', type=Path, required=True)
    for name in ("preflight", "derive", "measure", "package"):
        p = commands.add_parser(name)
        p.add_argument("recipe", type=Path)
        if name != "preflight":
            p.add_argument("--output", type=Path, required=True)
        if name == "measure":
            p.add_argument("--candidate", type=Path)
        if name == "package":
            p.add_argument("--file", action="append", type=Path, required=True)
    for name in ('compare', 'compare-models'):
        p = commands.add_parser(name)
        p.add_argument("baseline", type=Path)
        p.add_argument("candidate", type=Path)
        p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("review")
    p.add_argument("packet", type=Path)
    p.add_argument("--status", choices=("accepted", "rejected", "pending"), required=True)
    p.add_argument("--reviewer", default="")
    p.add_argument("--note", required=True)
    p.add_argument("--evidence", type=Path, action="append", default=[])
    p.add_argument("--cleanup-minutes", type=float, default=0)
    p.add_argument('--clip', action='append', help='Review these clips; omission means the entire packet')
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("summary")
    p.add_argument("reviews", nargs="+", type=Path)


def dispatch(args):
    name = args.animation_command
    if name == 'init':
        from .animation_profiles import create_recipe, parse_inputs
        return create_recipe(args.profile, args.output, parse_inputs(args.input))
    if name == "preflight":
        return preflight(args.recipe)
    if name == "derive":
        return derive(args.recipe, args.output)
    if name == "measure":
        return measure(args.recipe, args.output, args.candidate)
    if name == "compare":
        return compare(args.baseline, args.candidate, args.output)
    if name == 'compare-models':
        return compare_models(args.baseline, args.candidate, args.output)
    if name == "review":
        return record_review(args.packet, args.status, args.reviewer, args.note, args.evidence,
                             args.cleanup_minutes, args.output, args.clip)
    if name == "summary":
        return review_summary(args.reviews)
    if name == "package":
        return package(args.recipe, args.file, args.output)
    raise ValueError(f"unknown animation command: {name}")
