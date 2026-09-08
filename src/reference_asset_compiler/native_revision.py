"""Revalidate native engine derivatives without rewriting their source import history."""
from pathlib import Path

from .io import read_json, sha256_file


def validate_matched_native_frames(gallery, mesh, vertices):
    """Require two unobstructed, forced-LOD0 pairs bound to the verified mesh."""
    if (gallery.get("schema") != "reference-asset-compiler.ue-native-matched-review.v1"
            or gallery.get("error") is not None or gallery.get("forced_lod_model") != 1
            or gallery.get("assets", {}).get("reduced", {}).get("path") != mesh
            or gallery["assets"]["reduced"].get("lod0_vertices") != vertices
            or not gallery.get("level")):
        raise ValueError("Matched review does not identify the verified native derivative")
    frames = gallery.get("frames") or []
    if len(frames) != 4:
        raise ValueError("Matched review requires two complete camera pairs")
    paths = []
    for i in range(0, 4, 2):
        original, reduced = frames[i:i+2]
        if (original.get("mesh") != gallery["assets"]["original"]["path"]
                or reduced.get("mesh") != mesh
                or any(original.get(key) != reduced.get(key) or original.get(key) is None
                       for key in ("camera_position", "camera_pitch_yaw", "actor_position"))):
            raise ValueError("Matched review camera pair is not matched to the native meshes")
        for row in (original, reduced):
            path = Path(row.get("path", ""))
            if (row.get("forced_lod_model") != 1 or not path.is_file()
                    or sha256_file(path) != row.get("sha256")):
                raise ValueError("Matched native frame is missing, changed or not LOD0")
            paths.append(path.resolve())
    if len(set(paths)) != 4 or frames[0]["camera_position"] == frames[2]["camera_position"]:
        raise ValueError("Matched native review repeats a frame or viewpoint")
    return paths


def validate_native_revision(payload, evidence, maximum_vertices, maximum_triangles):
    if payload.get('native_revision', {}).get('derivative', {}).get('operation') == 'native_material_rebind':
        return validate_material_revision(payload, evidence, maximum_vertices, maximum_triangles)
    revision = payload.get("native_revision")
    if not isinstance(revision, dict):
        raise ValueError("Native revision metadata is missing")
    indexed = {str(p.resolve()): sha256_file(p) for p in evidence}

    def bound(row):
        if not isinstance(row, dict) or not row.get("path") or not row.get("sha256"):
            raise ValueError("Native revision has a malformed artifact")
        path = Path(row["path"]).resolve()
        if indexed.get(str(path)) != row["sha256"]:
            raise ValueError("Native revision artifact is missing or changed")
        return path

    previous = read_json(bound(revision.get("previous_import")))
    derivative = revision.get("derivative") or {}
    result = payload.get("result") or {}
    if (previous.get("schema") != "reference-asset-compiler.ue5-import-evidence.v1"
            or previous.get("ok") is not True
            or previous.get("manifest_sha256") != payload.get("manifest_sha256")
            or previous.get("asset_id") != payload.get("asset_id")
            or derivative.get("source_manifest_sha256") != payload.get("manifest_sha256")
            or derivative.get("source_mesh") != previous.get("result", {}).get("mesh")
            or not derivative.get("candidate_mesh")
            or derivative["candidate_mesh"] == derivative.get("source_mesh")
            or derivative["candidate_mesh"] != result.get("mesh")
            or derivative.get("operation") != "native_lod_reduction"
            or derivative.get("material_interfaces_identical") is not True):
        raise ValueError("Native revision is not a same-material derivative of the previous import")
    interfaces = derivative.get("material_interfaces")
    if not isinstance(interfaces, list) or len(interfaces) != 2 or not interfaces[0] or interfaces[0] != interfaces[1]:
        raise ValueError("Native revision material identity is unproven")
    native_files = derivative.get("native_files") or []
    if {r.get("mesh") for r in native_files} != {derivative["source_mesh"], derivative["candidate_mesh"]}:
        raise ValueError("Native revision must bind both native meshes")
    for row in native_files:
        if bound(row).suffix != ".uasset":
            raise ValueError("Native revision requires native uasset files")
    artifacts = derivative.get("artifacts") or []
    if not artifacts:
        raise ValueError("Native revision lacks transformation receipts")
    for row in artifacts:
        bound(row)
    transforms = [read_json(bound(row)) for row in artifacts]
    reduction = transforms[0]
    if (reduction.get("schema") not in {"reference-asset-compiler.board-runtime-reduction.v1",
                                       "reference-asset-compiler.native-lod-reduction.v1"}
            or reduction.get("source_mesh") != derivative["source_mesh"]
            or reduction.get("triangle_fractions") != derivative.get("triangle_fractions")
            or reduction.get("original_asset_preserved") is not True):
        raise ValueError("Native revision reduction lineage is unproven")
    terminal_mesh = reduction.get("candidate_mesh")
    for transform in transforms[1:]:
        if (transform.get("schema") != "reference-asset-compiler.native-scale-normalization.v1"
                or transform.get("source_mesh") != terminal_mesh
                or transform.get("source_preserved") is not True
                or not 0 < transform.get("uniform_build_scale_factor", 0)
                or not transform.get("candidate_mesh")):
            raise ValueError("Native revision normalization lineage is unproven")
        terminal_mesh = transform["candidate_mesh"]
    if terminal_mesh != derivative["candidate_mesh"]:
        raise ValueError("Native revision transformation chain ends at a different mesh")
    bound({"path": payload.get("batch_report"), "sha256": payload.get("batch_report_sha256")})
    batch = read_json(Path(payload["batch_report"]))
    if batch.get("native_derivative") != derivative or result not in batch.get("assets", []):
        raise ValueError("Native revision disagrees with its native verification report")
    rows = result.get("native_lods") or []
    if (not maximum_vertices or not maximum_triangles or not rows
            or len(rows) != result.get("lod_count")
            or [row.get("lod") for row in rows] != list(range(len(rows)))
            or any(not 0 < row.get("vertices", 0) <= maximum_vertices
                   or not 0 < row.get("triangles", 0) <= maximum_triangles for row in rows)):
        raise ValueError("Native revision exceeds runtime budgets or lacks built LOD counts")
    required = {"import_scale", "materials_assigned", "materials_textured", "lods",
                "native_runtime_budget", "texture_settings", "derivative_material_identity"}
    checks = {row.get("check"): row.get("ok") for row in result.get("checks", [])}
    if any(checks.get(name) is not True for name in required):
        raise ValueError("Native revision lacks mandatory engine checks")


def validate_material_revision(payload, evidence, maximum_vertices, maximum_triangles):
    """A material fix may change its coat, never silently change the mesh underneath."""
    indexed = {str(p.resolve()): sha256_file(p) for p in evidence}

    def bound(row):
        if not isinstance(row, dict) or not row.get('path') or not row.get('sha256'):
            raise ValueError('Material revision has an unbound artifact')
        path = Path(row['path']).resolve()
        if indexed.get(str(path)) != row['sha256']:
            raise ValueError('Material revision artifact is missing or changed')
        return path

    revision = payload['native_revision']
    derivative = revision['derivative']
    previous = read_json(bound(revision.get('previous_import')))
    result = payload.get('result') or {}
    if (previous.get('schema') != 'reference-asset-compiler.ue5-import-evidence.v1'
            or previous.get('ok') is not True or previous.get('asset_id') != payload.get('asset_id')
            or previous.get('manifest_sha256') != payload.get('manifest_sha256')
            or derivative.get('source_manifest_sha256') != payload.get('manifest_sha256')
            or derivative.get('source_mesh') != previous.get('result', {}).get('mesh')
            or not derivative.get('candidate_mesh')
            or derivative['candidate_mesh'] == derivative.get('source_mesh')
            or derivative['candidate_mesh'] != result.get('mesh')):
        raise ValueError('Material revision source import lineage is unproven')
    native = derivative.get('native_files') or []
    if len(native) != 2 or {row.get('mesh') for row in native} != {derivative['source_mesh'], derivative['candidate_mesh']}:
        raise ValueError('Material revision must bind both native meshes')
    for row in native:
        if bound(row).suffix != '.uasset':
            raise ValueError('Material revision requires native mesh files')
    materials = derivative.get('material_files') or []
    if len(materials) < 3 or len({row.get('path') for row in materials}) != len(materials):
        raise ValueError('Material revision lacks distinct original, replacement and master files')
    for row in materials:
        if bound(row).suffix != '.uasset':
            raise ValueError('Material revision requires native material files')
    artifacts = derivative.get('artifacts') or []
    if len(artifacts) != 1:
        raise ValueError('Material revision needs one native buffer and binding probe')
    probe = read_json(bound(artifacts[0]))
    rows = probe.get('assets') or []
    if (len(rows) != 2 or rows[0].get('mesh') != derivative['source_mesh']
            or rows[1].get('mesh') != derivative['candidate_mesh']
            or probe.get('geometry_identical') is not True or probe.get('read_only') is not True
            or not rows[0].get('lods') or rows[0]['lods'] != rows[1].get('lods')
            or not rows[0].get('textures') or rows[0]['textures'] != rows[1].get('textures')
            or rows[0].get('material') == rows[1].get('material')
            or rows[0].get('parent') == rows[1].get('parent')):
        raise ValueError('Material revision must preserve actual geometry buffers and authored textures')
    native_paths = {row.get('asset') for row in materials}
    if not {rows[0]['material'], rows[1]['material'], rows[1]['parent']}.issubset(native_paths):
        raise ValueError('Material file bindings disagree with the engine probe')
    lods = result.get('native_lods') or []
    if (not maximum_vertices or not maximum_triangles or len(lods) != result.get('lod_count')
            or len(lods) != len(rows[0]['lods'])
            or [r.get('lod') for r in lods] != list(range(len(lods)))):
        raise ValueError('Material revision lacks all built LODs')
    for measured, built in zip(rows[0]['lods'], lods):
        if (len(measured.get('sha256', '')) != 64
                or measured.get('vertices') != built.get('vertices')
                or measured.get('triangles') != built.get('triangles')
                or not 0 < built.get('vertices', 0) <= maximum_vertices
                or not 0 < built.get('triangles', 0) <= maximum_triangles):
            raise ValueError('Material revision geometry measurements or budgets disagree')
    batch = read_json(bound({'path': payload.get('batch_report'), 'sha256': payload.get('batch_report_sha256')}))
    if batch.get('native_derivative') != derivative or result not in batch.get('assets', []):
        raise ValueError('Material revision disagrees with its verification report')
    checks = {row.get('check'): row.get('ok') for row in result.get('checks', [])}
    required = {'import_scale', 'materials_assigned', 'materials_textured', 'lods',
                'native_runtime_budget', 'texture_settings', 'normal_fallback_policy'}
    if result.get('ok') is not True or any(checks.get(name) is not True for name in required):
        raise ValueError('Material revision lacks required engine checks')
