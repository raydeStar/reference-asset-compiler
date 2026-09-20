"""Texture binding in the browser payload stage.

A production package renames its textures on the way out and packs occlusion,
roughness and metallic into one image, so the names an FBX carries no longer
match the files beside it. Binding by name therefore finds nothing and the
payload exports with correct geometry and no colour, which reads as a broken
asset rather than a missing file. The stage reads the import manifest instead.

The stage runs inside Blender. Only the binding decisions are exercised here,
under a stub ``bpy``, so a regression is caught without a Blender round trip.
"""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

STAGES = Path(__file__).resolve().parents[1] / "scripts" / "blender"

NODE_TYPES = {
    "ShaderNodeBsdfPrincipled": "BSDF_PRINCIPLED",
    "ShaderNodeOutputMaterial": "OUTPUT_MATERIAL",
    "ShaderNodeTexImage": "TEX_IMAGE",
    "ShaderNodeSeparateColor": "SEPARATE_COLOR",
}


class Socket:
    def __init__(self, node, name):
        self.node = node
        self.name = name


class Sockets(dict):
    def __init__(self, node):
        super().__init__()
        self.node = node

    def __getitem__(self, name):
        if name not in self:
            self[name] = Socket(self.node, name)
        return dict.__getitem__(self, name)


class Node:
    def __init__(self, idname):
        self.type = NODE_TYPES.get(idname, idname)
        self.image = None
        self.inputs = Sockets(self)
        self.outputs = Sockets(self)


class Nodes(list):
    def __init__(self, tree):
        super().__init__()
        self.tree = tree

    def new(self, idname):
        node = Node(idname)
        self.append(node)
        return node

    def remove(self, node):
        # Blender drops a removed node's links with it; a stub that leaves them
        # behind reports connections the real tree no longer has.
        for link in list(self.tree.links):
            if link.from_socket.node is node or link.to_socket.node is node:
                self.tree.links.remove(link)
        list.remove(self, node)


class Link:
    def __init__(self, from_socket, to_socket):
        self.from_socket = from_socket
        self.to_socket = to_socket


class Links(list):
    def new(self, source, target):
        # An input takes one link; a second replaces the first, as Blender does.
        for existing in list(self):
            if existing.to_socket is target:
                self.remove(existing)
        link = Link(source, target)
        self.append(link)
        return link


class Tree:
    def __init__(self):
        self.links = Links()
        self.nodes = Nodes(self)


class Material:
    def __init__(self, name, principled=True):
        self.name = name
        self.use_nodes = True
        self.node_tree = Tree()
        if principled:
            surface = self.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            output = self.node_tree.nodes.new("ShaderNodeOutputMaterial")
            self.node_tree.links.new(surface.outputs["BSDF"], output.inputs["Surface"])

    def source_of(self, input_name):
        """The node feeding one of this material's surface inputs, if any."""
        for link in self.node_tree.links:
            if link.to_socket.name == input_name and link.to_socket.node.type == "BSDF_PRINCIPLED":
                return link.from_socket.node
        return None

    def feeds(self, node, input_name):
        """Whether a node reaches the named surface input, directly or through one hop."""
        direct = self.source_of(input_name)
        if direct is node:
            return True
        if direct is None:
            return False
        for link in self.node_tree.links:
            if link.to_socket.node is direct and link.from_socket.node is node:
                return True
        return False

    def preview_bind(self, image_name, *input_names):
        """What an authoring file leaves behind: one image wired into several slots."""
        node = self.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = Image(image_name)
        surface = next(n for n in self.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        for name in input_names:
            self.node_tree.links.new(node.outputs["Color"], surface.inputs[name])
        return node


class Image:
    def __init__(self, filepath):
        self.filepath = str(filepath)
        self.name = Path(filepath).stem
        self.packed_file = None
        self.colorspace_settings = types.SimpleNamespace(name="sRGB")
        self.reloaded = 0

    def reload(self):
        self.reloaded += 1


class Images(list):
    def load(self, filepath, check_existing=False):
        if check_existing:
            for image in self:
                if image.filepath == str(filepath):
                    return image
        image = Image(filepath)
        self.append(image)
        return image

    def remove(self, image):
        list.remove(self, image)


class Materials(list):
    def get(self, name):
        return next((m for m in self if m.name == name), None)


def load_stage():
    saved = sys.modules.get("bpy")
    bpy = types.ModuleType("bpy")
    bpy.data = types.SimpleNamespace(materials=Materials(), images=Images())
    bpy.ops = types.SimpleNamespace()
    bpy.path = types.SimpleNamespace(abspath=lambda p: p)
    sys.modules["bpy"] = bpy
    try:
        spec = importlib.util.spec_from_file_location(
            "export_browser_payload", STAGES / "export_browser_payload.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("bpy", None)
        else:
            sys.modules["bpy"] = saved
    module.bpy = bpy
    return module, bpy


class TextureBindingTests(unittest.TestCase):
    def setUp(self):
        self.stage, self.bpy = load_stage()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "textures").mkdir()

    def texture(self, name):
        (self.root / "textures" / name).write_bytes(b"png")
        return "textures/" + name

    def manifest(self, source, textures):
        source.with_suffix(".ue5import.json").write_text(
            json.dumps({"textures": textures}), encoding="utf-8")

    def source(self, name="asset.fbx"):
        path = self.root / name
        path.write_bytes(b"fbx")
        return path

    def test_a_renamed_production_texture_is_found_through_the_manifest(self):
        material = Material("M_Thing_Body")
        self.bpy.data.materials.append(material)
        source = self.source()
        self.manifest(source, {"M_Thing_Body": {
            "BaseColor": {"file": self.texture("T_ThingProduction_BaseColor.png")},
            "ORM": {"file": self.texture("T_ThingProduction_ORM.png")},
        }})

        report = {}
        self.stage.bind_manifest_textures(source, report)

        # The names in the manifest bear no resemblance to the material's own,
        # which is exactly why matching by name finds nothing.
        self.assertEqual(report["textures_bound"], ["M_Thing_Body.BaseColor", "M_Thing_Body.ORM"])
        self.assertEqual(report["textures_missing"], [])
        self.assertNotIn("material_matched_by_position", report)

    def test_base_colour_is_read_as_colour_and_the_pack_is_read_as_numbers(self):
        self.bpy.data.materials.append(Material("M_Thing_Body"))
        source = self.source()
        self.manifest(source, {"M_Thing_Body": {
            "BaseColor": {"file": self.texture("base.png")},
            "ORM": {"file": self.texture("orm.png")},
        }})

        self.stage.bind_manifest_textures(source, {})

        base = next(i for i in self.bpy.data.images if i.name == "base")
        orm = next(i for i in self.bpy.data.images if i.name == "orm")
        # Getting this backwards double-applies the transfer function, so the
        # model looks washed out rather than obviously wrong.
        self.assertEqual(base.colorspace_settings.name, "sRGB")
        self.assertEqual(orm.colorspace_settings.name, "Non-Color")

    def test_the_pack_reaches_roughness_and_metallic_but_never_base_colour(self):
        material = Material("M_Thing_Body")
        self.bpy.data.materials.append(material)
        source = self.source()
        self.manifest(source, {"M_Thing_Body": {
            "BaseColor": {"file": self.texture("base.png")},
            "ORM": {"file": self.texture("orm.png")},
        }})

        self.stage.bind_manifest_textures(source, {})

        nodes = material.node_tree.nodes
        base_node = next(n for n in nodes if n.image is not None and n.image.name == "base")
        orm_node = next(n for n in nodes if n.image is not None and n.image.name == "orm")
        split = next(n for n in nodes if n.type == "SEPARATE_COLOR")

        self.assertTrue(material.feeds(base_node, "Base Color"))
        # Green and blue of the pack, which is the arrangement glTF stores, so
        # the exporter recognises it and writes one metallicRoughness texture.
        self.assertIs(material.source_of("Roughness"), split)
        self.assertIs(material.source_of("Metallic"), split)
        self.assertTrue(material.feeds(orm_node, "Roughness"))
        self.assertFalse(material.feeds(orm_node, "Base Color"))

    def test_one_material_and_one_entry_bind_despite_disagreeing_names(self):
        # A package that names its material after itself rather than the mesh.
        self.bpy.data.materials.append(Material("M_Sword_Body"))
        source = self.source()
        self.manifest(source, {"M_Sword_Production": {
            "BaseColor": {"file": self.texture("sword.png")},
        }})

        report = {}
        self.stage.bind_manifest_textures(source, report)

        self.assertEqual(report["textures_bound"], ["M_Sword_Production.BaseColor"])
        # The substitution is recorded, not silently assumed.
        self.assertEqual(report["material_matched_by_position"], "M_Sword_Body")

    def test_a_name_that_matches_nothing_is_not_guessed_when_there_is_a_choice(self):
        self.bpy.data.materials.extend([Material("M_Head"), Material("M_Hair")])
        source = self.source()
        self.manifest(source, {"M_Absent": {"BaseColor": {"file": self.texture("x.png")}}})

        report = {}
        self.stage.bind_manifest_textures(source, report)

        # Two candidates, so a guess would have an even chance of painting the
        # wrong surface. Refusing and saying so is the only honest answer.
        self.assertEqual(report["textures_bound"], [])
        self.assertEqual(report["textures_missing"], ["M_Absent (no such material in the file)"])
        self.assertNotIn("material_matched_by_position", report)

    def test_a_manifest_naming_a_file_that_is_not_there_reports_it(self):
        self.bpy.data.materials.append(Material("M_Thing_Body"))
        source = self.source()
        self.manifest(source, {"M_Thing_Body": {
            "BaseColor": {"file": self.texture("present.png")},
            "ORM": {"file": "textures/absent.png"},
        }})

        report = {}
        self.stage.bind_manifest_textures(source, report)

        self.assertEqual(report["textures_bound"], ["M_Thing_Body.BaseColor"])
        self.assertEqual(report["textures_missing"], ["M_Thing_Body.ORM -> textures/absent.png"])

    def test_without_a_manifest_a_staged_asset_relinks_by_name(self):
        self.bpy.data.materials.append(Material("M_Thing_Body"))
        source = self.source()
        self.texture("T_Thing_BaseColor.png")
        # What an FBX carries: an absolute path from the machine that made it.
        self.bpy.data.images.append(Image("D:/elsewhere/T_Thing_BaseColor.png"))

        report = {}
        self.stage.bind_manifest_textures(source, report)

        self.assertEqual(report["textures_relinked"], ["T_Thing_BaseColor.png"])
        self.assertEqual(report["textures_missing"], [])
        self.assertTrue(Path(self.bpy.data.images[0].filepath).is_file())

    def test_an_unreadable_manifest_falls_back_rather_than_stopping(self):
        self.bpy.data.materials.append(Material("M_Thing_Body"))
        source = self.source()
        source.with_suffix(".ue5import.json").write_text("{ not json", encoding="utf-8")

        report = {}
        self.stage.bind_manifest_textures(source, report)

        self.assertIn("texture_manifest_error", report)
        self.assertIn("textures_relinked", report)


class NamedManifestTests(unittest.TestCase):
    """An assembled working file carries a preview material, not a production one."""

    def setUp(self):
        self.stage, self.bpy = load_stage()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "textures").mkdir()

    def texture(self, name):
        (self.root / "textures" / name).write_bytes(b"png")
        return "textures/" + name

    def test_a_named_manifest_is_read_instead_of_one_beside_the_source(self):
        self.bpy.data.materials.append(Material("M_Preview"))
        blend = self.root / "assembly-fit.blend"
        blend.write_bytes(b"blend")
        # The manifest belongs to the package the body was exported as, which
        # lives nowhere near the blend that assembled it.
        elsewhere = self.root / "package.ue5import.json"
        elsewhere.write_text(json.dumps({"textures": {"M_Preview": {
            "BaseColor": {"file": self.texture("body_BaseColor.png")},
            "ORM": {"file": self.texture("body_ORM.png")},
        }}}), encoding="utf-8")

        report = {}
        self.stage.bind_manifest_textures(blend, report, elsewhere)

        self.assertEqual(report["textures_bound"], ["M_Preview.BaseColor", "M_Preview.ORM"])
        self.assertEqual(report["texture_manifest"], str(elsewhere))

    def test_a_preview_network_is_removed_rather_than_bound_over(self):
        material = Material("M_Preview")
        self.bpy.data.materials.append(material)
        # Exactly what the neck-transfer material does: the paint wired into
        # metallic-roughness and normal as well as into colour. Left there, the
        # blue channel of blue armour becomes metalness and the model goes black.
        preview = material.preview_bind("paint", "Base Color", "Roughness", "Metallic", "Normal")
        blend = self.root / "assembly-fit.blend"
        blend.write_bytes(b"blend")
        manifest = self.root / "package.ue5import.json"
        manifest.write_text(json.dumps({"textures": {"M_Preview": {
            "BaseColor": {"file": self.texture("body_BaseColor.png")},
        }}}), encoding="utf-8")

        self.stage.bind_manifest_textures(blend, {}, manifest)

        bound = next(n for n in material.node_tree.nodes
                     if n.image is not None and n.image.name == "body_BaseColor")
        self.assertIs(material.source_of("Base Color"), bound)
        # Slots the manifest says nothing about must not keep the preview's
        # answer, and the preview's nodes must be gone rather than merely
        # unhooked: an orphaned network is still something the exporter reads.
        for slot in ("Roughness", "Metallic", "Normal"):
            self.assertIsNone(material.source_of(slot), slot)
        self.assertNotIn(preview, material.node_tree.nodes)
        self.assertEqual([n for n in material.node_tree.nodes if n.type == "TEX_IMAGE"], [bound])

    def test_rebuilding_keeps_the_material_output_it_found(self):
        material = Material("M_Preview")
        self.bpy.data.materials.append(material)
        material.preview_bind("paint", "Base Color")
        output = next(n for n in material.node_tree.nodes if n.type == "OUTPUT_MATERIAL")
        blend = self.root / "assembly-fit.blend"
        blend.write_bytes(b"blend")
        manifest = self.root / "package.ue5import.json"
        manifest.write_text(json.dumps({"textures": {"M_Preview": {
            "BaseColor": {"file": self.texture("body_BaseColor.png")},
        }}}), encoding="utf-8")

        self.stage.bind_manifest_textures(blend, {}, manifest)

        # A material with nothing reaching its output exports as no surface at
        # all, which is a worse failure than the one being fixed.
        self.assertIn(output, material.node_tree.nodes)
        surface = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        self.assertTrue(any(link.from_socket.node is surface and link.to_socket.node is output
                            for link in material.node_tree.links))

    def test_a_named_manifest_that_is_not_there_says_so(self):
        self.bpy.data.materials.append(Material("M_Preview"))
        blend = self.root / "assembly-fit.blend"
        blend.write_bytes(b"blend")

        report = {}
        self.stage.bind_manifest_textures(blend, report, self.root / "absent.json")

        # Silently falling back to name matching would export a preview surface
        # while the caller believed a production one had been applied.
        self.assertIn("no such manifest", report["texture_manifest_error"])


class DeadImageTests(unittest.TestCase):
    def setUp(self):
        self.stage, self.bpy = load_stage()
        self.root = Path(tempfile.mkdtemp())

    def test_images_pointing_nowhere_are_forgotten(self):
        real = self.root / "real.png"
        real.write_bytes(b"png")
        kept = Image(real)
        self.bpy.data.images.extend([kept, Image("D:/gone/T_Old_BaseColor.png")])

        report = {}
        self.stage.drop_dead_images(report)

        # Left in place these make packing fail for files nobody wants, and can
        # leave the payload pointing at a path that exists on no other machine.
        self.assertEqual(report["textures_dropped"], ["T_Old_BaseColor.png"])
        self.assertEqual(list(self.bpy.data.images), [kept])

    def test_a_packed_image_is_kept_even_with_no_file_behind_it(self):
        packed = Image("D:/gone/already-inside.png")
        packed.packed_file = object()
        self.bpy.data.images.append(packed)

        report = {}
        self.stage.drop_dead_images(report)

        # Its pixels are already in the file; the path is only where it came from.
        self.assertNotIn("textures_dropped", report)
        self.assertEqual(list(self.bpy.data.images), [packed])


if __name__ == "__main__":
    unittest.main()
