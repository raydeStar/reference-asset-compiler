"""Transient, repeatable editor review; no level save and no gameplay claim.

Call setup(mesh_path, groom_path), then capture(path) on a later editor tick.
Call cleanup() after reviewing. References keep the transient stage alive.

Dependency: capture() renders through The Aether Wars' editor tooling
(``aether_mcp_tools.toolsets.dungeon._export_camera_render_target``, from that
game's private AetherMcpTools plugin), which is not part of this repository.
setup(), use_blueprint() and cleanup() need only Unreal's own Python API; in
another project, capture the review camera with your own render-target export.
"""
import json
from pathlib import Path

import unreal

ACTORS = []
BODY = HAIR = CAMERA = None


def cleanup():
    editor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in ACTORS:
        if actor:
            editor.destroy_actor(actor)
    ACTORS.clear()


def setup(mesh_path, groom_path):
    global BODY, HAIR, CAMERA
    cleanup()
    editor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def spawn(cls, location):
        actor = editor.spawn_actor_from_class(cls, unreal.Vector(*location), transient=True)
        ACTORS.append(actor)
        return actor

    BODY = spawn(unreal.SkeletalMeshActor, (0, 0, 20000))
    BODY.skeletal_mesh_component.set_skeletal_mesh_asset(unreal.load_asset(mesh_path))
    HAIR = spawn(unreal.GroomActor, (0, 0, 20000))
    HAIR.groom_component.set_groom_asset(unreal.load_asset(groom_path))
    HAIR.groom_component.set_enable_simulation(False)
    for slot in BODY.skeletal_mesh_component.skeletal_mesh.materials:
        # Camera captures do not drive texture streaming like a live viewport.
        for tex in unreal.MaterialEditingLibrary.get_used_textures(slot.material_interface):
            tex.set_force_mip_levels_to_be_resident(600, 0)
    for location, intensity, colour in (((-120, 180, 20250), 75, (1, .95, .90)),
                                      ((150, 80, 20160), 65, (.85, .90, 1)),
                                      ((0, -100, 20220), 55, (1, .90, .8))):
        actor = spawn(unreal.PointLight, location)
        actor.point_light_component.set_intensity(intensity)
        actor.point_light_component.set_attenuation_radius(1000)
        actor.point_light_component.set_light_color(unreal.LinearColor(*colour, 1))
    CAMERA = spawn(unreal.CameraActor, (0, 360, 20100))
    CAMERA.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(CAMERA.get_actor_location(), unreal.Vector(0, 0, 20095)), False)
    CAMERA.camera_component.field_of_view = 40
    print('Transient review stage ready; no furniture has moved downstairs, sir.')


def capture(path):
    try:
        import aether_mcp_tools.toolsets.dungeon as dg
    except ImportError as error:
        raise RuntimeError("capture() needs The Aether Wars' AetherMcpTools editor plugin "
                           "(aether_mcp_tools); see this module's docstring") from error
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = dg._export_camera_render_target(CAMERA, 1024, 1024, str(path))
    bounds = {}
    for name, actor in (("body", BODY), ("hair", HAIR)):
        component = actor.get_component_by_class(unreal.SkeletalMeshComponent if name == 'body' else unreal.GroomComponent)
        centre, extent, _ = unreal.SystemLibrary.get_component_bounds(component)
        bounds[name] = {"centre": [centre.x, centre.y, centre.z], "extent": [extent.x, extent.y, extent.z]}
    path.with_suffix('.json').write_text(json.dumps({"capture": result, "bounds": bounds, "runtime_verified": False}, indent=2))
    print(result, bounds)


def use_blueprint(path):
    """Replace the loose import previews with the actual combined review asset."""
    global BODY, HAIR
    editor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in (BODY, HAIR):
        editor.destroy_actor(actor)
        ACTORS.remove(actor)
    cls = unreal.EditorAssetLibrary.load_blueprint_class(path)
    actor = editor.spawn_actor_from_class(cls, unreal.Vector(0, 0, 20000), transient=True)
    ACTORS.append(actor)
    BODY = HAIR = actor
    # This editor preview switch is transient; setting it on the Blueprint
    # template alone does not survive spawning. Runtime animation is separate.
    actor.get_component_by_class(unreal.SkeletalMeshComponent).set_update_animation_in_editor(True)
