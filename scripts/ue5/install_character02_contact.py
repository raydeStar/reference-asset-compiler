# SPDX-License-Identifier: MIT
"""Install only the seven reviewed Character02 clip edits, retaining exact backups.

Use in a fresh commandlet with RAC_CONTACT_PACKET and RAC_CONTACT_DERIVATION.
No graph, mesh, montage, timing, gameplay-event or root-motion changes.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

import unreal

ROOT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
sys.path.insert(0, str(ROOT / 'Tools'))
import CharacterInstall as ci  # noqa: E402 - project-local Unreal helpers
import LibraryAnims as la  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ci.configure('Tools/Characters/Character02.json')
    candidate = Path(os.environ['RAC_CONTACT_PACKET'])
    derivation_path = Path(os.environ['RAC_CONTACT_DERIVATION'])
    derivation = json.loads(derivation_path.read_text())
    assert sha(candidate) == derivation['packet_sha256']
    source = ROOT / ci.CHARACTER['library_anims']['packet'] / 'clips.json'
    assert sha(source) == derivation['source_sha256'], 'Installed selection changed; do not overwrite another revision'
    data = json.loads(candidate.read_text())
    modified = derivation['modified_clips']
    assert set(modified) == {'MM_Idle', 'MF_Unarmed_Walk_Fwd', 'MM_Start', 'MM_Stop_L', 'MM_Stop_R', 'MM_Jump', 'MM_Land'}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'Saved/AnimationContactRepair' / stamp
    out.mkdir(parents=True, exist_ok=False)
    targets = [(f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}{alias}', data['clips'][name])
               for name in modified for alias in [name] + data['clips'][name].get('also_as', [])]
    receipt = {'source_sha256': sha(source), 'candidate_sha256': sha(candidate), 'before': {},
               'readback': {}, 'human_approved': False, 'production_ready': False, 'error': None}
    config = ROOT / 'Tools/Characters/Character02.json'
    shutil.copy2(config, out / 'Character02.before.json')
    for path, _ in targets:
        rel = Path('Content') / (path.removeprefix('/Game/') + '.uasset')
        backup = out / 'backup' / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, backup)
        receipt['before'][rel.as_posix()] = sha(backup)
    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    save()
    try:
        mesh = unreal.load_asset(ci.MESH)
        bones = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(
            unreal.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property('skeleton')))]
        for path, clip in targets:
            seq = unreal.load_asset(path)
            assert seq, path
            before_events = [(str(e.get_editor_property('notify_name')), unreal.AnimationLibrary.get_anim_notify_event_trigger_time(e))
                             for e in unreal.AnimationLibrary.get_animation_notify_events(seq)]
            la._key(seq, clip, bones)
            cm, degrees = la._readback(seq, clip, bones)
            assert cm < .05 and degrees < .1, (path, cm, degrees)
            after_events = [(str(e.get_editor_property('notify_name')), unreal.AnimationLibrary.get_anim_notify_event_trigger_time(e))
                            for e in unreal.AnimationLibrary.get_animation_notify_events(seq)]
            assert before_events == after_events
            receipt['readback'][path] = {'cm': cm, 'degrees': degrees, 'events_unchanged': True}
            save()
        selected = ROOT / 'Saved/LibraryAnims/Character02' / ('ual-v22-idle-contact-' + stamp)
        shutil.copytree(source.parent, selected)
        shutil.copy2(candidate, selected / 'clips.json')
        shutil.copy2(derivation_path, selected / 'idle-contact-derivation.json')
        packet = selected.relative_to(ROOT).as_posix()
        ci.CHARACTER['library_anims']['packet'] = packet
        ci.CHARACTER['animation_flow']['packet'] = packet
        ci.CHARACTER['_idle_contact_repair'] = {'packet': packet, 'receipt': out.relative_to(ROOT).as_posix(),
            'human_approved': False, 'note': 'Relaxed idle, coat clearance and matching arm handoffs. Existing runtime clearance retained; Attack 03 unchanged.'}
        config.write_text(json.dumps(ci.CHARACTER, indent=2) + '\n')
        receipt['selected_packet'] = packet
        receipt['after'] = {rel: sha(ROOT / rel) for rel in receipt['before']}
        receipt['configuration_sha256'] = sha(config)
    except Exception:
        receipt['error'] = traceback.format_exc()
        raise
    finally:
        save()
    print('CONTACT_REPAIR_INSTALLED', out, '-- the original tailoring is safely in the wardrobe.')


main()
