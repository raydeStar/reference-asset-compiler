"""Preparing a mesh somebody has already reviewed.

A generated mesh and a library mesh need opposite handling, and the difference
is the whole of this route.

A generator's output has no topology worth keeping, so it is rebuilt on a grid
and repainted from scratch. A mesh already in somebody's library is the other
way round: its UVs, its materials and its shell are what somebody approved, and
a preparation that rebuilt any of them would be throwing away the review. So
this route adopts it unchanged, collapses it with its UVs and materials riding
along, and renders the fixed views a person compares the two by.

What is exercised here is the shaping and the refusals, which is where the
mistakes are. Nothing here runs Blender.
"""
import sys
import tempfile
import unittest
from pathlib import Path

from reference_asset_compiler.stages import (
    STAGES,
    prepare_adopt_mesh,
    prepare_reduction,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "blender"))
from reduction_verdict import is_open, surface_verdict  # noqa: E402

CLOSED = {"boundary_edges": 0, "nonmanifold_edges": 0}
OPEN = {"boundary_edges": 3888, "nonmanifold_edges": 3888}
STILL_OPEN = {"boundary_edges": 2460, "nonmanifold_edges": 2743}


class AdoptionTests(unittest.TestCase):
    def test_adoption_writes_a_blend_because_the_reduction_opens_one(self):
        stage = STAGES["adopt-mesh"]

        # glTF is transport: it may split shared vertices at face-corner
        # normals, and the reduction stage is right to insist on a .blend with
        # exactly one mesh object. Something has to convert, and this is it.
        self.assertEqual(stage["output_suffix"], ".blend")
        self.assertEqual(stage["produces"], "reference-asset-compiler.adopted-mesh.v1")
        self.assertIn("blender", stage["needs"])

    def test_adoption_asks_for_nothing_it_was_not_given(self):
        # Every other shaping option on this route belongs to the reduction.
        # Adoption converts; a knob here would be a decision about somebody's
        # approved asset taken in the wrong place.
        self.assertEqual(prepare_adopt_mesh({})["arguments"], [])

    def test_uvs_can_be_insisted_on_before_anything_runs(self):
        prepared = prepare_adopt_mesh({"require_uvs": True})

        # Preserving the UVs is the entire reason this route exists. A mesh
        # with none should be refused by name, not delivered as a derivative
        # nobody can paint.
        self.assertEqual(prepared["arguments"], ["--require-uvs"])

    def test_a_caller_who_did_not_ask_does_not_get_the_refusal(self):
        for answer in (None, False, ""):
            with self.subTest(answer=answer):
                self.assertEqual(prepare_adopt_mesh({"require_uvs": answer})["arguments"], [])


class RuntimeDerivativeRequestTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = self.root / "adopted.blend"
        self.source.write_bytes(b"blend")
        self.output = self.root / "runtime.glb"

    def test_the_mode_reaches_the_launcher_as_a_switch(self):
        prepared = prepare_reduction(
            self.source, self.output, {"triangle_budget": 8000, "runtime_derivative": True})

        # A switch, not a setting: passing it a value would make PowerShell
        # read the next parameter name as this one's argument.
        arguments = prepared["arguments"]
        self.assertIn("-RuntimeDerivative", arguments)
        self.assertNotEqual(arguments[arguments.index("-RuntimeDerivative") - 1], "-RuntimeDerivative")
        self.assertEqual(arguments[arguments.index("-TriangleBudget") + 1], "8000")

    def test_an_authority_reduction_says_nothing_about_runtime(self):
        prepared = prepare_reduction(self.source, self.output, {"triangle_budget": 8000})

        # Silence means the launcher's own documented behaviour, which is the
        # strict authority gate. A relaxation has to be asked for.
        self.assertNotIn("-RuntimeDerivative", prepared["arguments"])

    def test_the_mode_is_something_the_stage_actually_offers(self):
        # A studio reads this list to know what it may ask for. An option the
        # registry does not name is one a caller cannot discover.
        self.assertIn("runtime_derivative", STAGES["reduce-mesh"]["options"])


class SurfaceVerdictTests(unittest.TestCase):
    """The one judgement in the reduction that is not arithmetic."""

    def test_a_closed_candidate_needs_no_allowance(self):
        for runtime in (False, True):
            with self.subTest(runtime=runtime):
                self.assertEqual(surface_verdict(OPEN, CLOSED, runtime), ([], []))

    def test_an_authority_candidate_is_still_judged_as_an_authority(self):
        failures, accepted = surface_verdict(OPEN, STILL_OPEN, runtime_derivative=False)

        # The strict gate is not softened for everybody just because one kind
        # of caller needed it softened for them.
        self.assertEqual(failures, ["candidate is not a closed two-manifold surface"])
        self.assertEqual(accepted, [])

    def test_an_inherited_opening_is_recorded_rather_than_rejected(self):
        failures, accepted = surface_verdict(OPEN, STILL_OPEN, runtime_derivative=True)

        # The source was open before anything ran. Rejecting the derivative for
        # it would be rejecting a mesh somebody already reviewed and accepted,
        # under the name of the reduction.
        self.assertEqual(failures, [])
        self.assertEqual(len(accepted), 1)
        # Both sides of the comparison, so a reader can see it got no worse.
        self.assertIn("2460", accepted[0])
        self.assertIn("3888", accepted[0])

    def test_a_surface_the_reduction_tore_open_is_still_a_failure(self):
        failures, accepted = surface_verdict(CLOSED, STILL_OPEN, runtime_derivative=True)

        # This is the check that stops "runtime derivative" from quietly
        # meaning "do not look". The allowance covers what the source already
        # was, never what the reduction did to it.
        self.assertEqual(accepted, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("opened a surface that was closed", failures[0])

    def test_either_kind_of_bad_edge_counts_as_open(self):
        # A surface with no boundary can still be non-manifold, and a mesh that
        # was only ever checked for boundaries would pass it.
        self.assertTrue(is_open({"boundary_edges": 0, "nonmanifold_edges": 4}))
        self.assertTrue(is_open({"boundary_edges": 4, "nonmanifold_edges": 0}))
        self.assertFalse(is_open(CLOSED))


if __name__ == "__main__":
    unittest.main()
