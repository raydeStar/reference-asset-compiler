"""The groom review's two measures, on small drawn renders instead of Blender's.

A game-look render and its id pass (strands red, scalp cap green, skin blue,
background black) are all the measures read: dark gaps between locks are hair
pixels much darker than the hair around them, and a ragged crown is the dense
mass's outline in the top half departing from a smooth one.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_groom_review import gap_measures  # noqa: E402

SIZE = 256


def head(lit=0.6):
    """A disc of hair over a disc of skin: an evenly lit, closed mass."""
    yy, xx = np.mgrid[:SIZE, :SIZE]
    hair = (xx - 128) ** 2 + (yy - 110) ** 2 < 90 ** 2
    skin = ((xx - 128) ** 2 + (yy - 150) ** 2 < 60 ** 2) & (yy > 120)
    ids = np.zeros((SIZE, SIZE, 3), np.float32)
    ids[hair & ~skin, 0] = 1.0
    ids[skin, 2] = 1.0
    beauty = np.full((SIZE, SIZE, 3), 0.35, np.float32)
    beauty[hair & ~skin] = lit
    return beauty, ids, hair & ~skin


class GapMeasureTests(unittest.TestCase):
    def measure(self, beauty, ids):
        with tempfile.TemporaryDirectory() as tmp:
            b, i = Path(tmp, "game-front.png"), Path(tmp, "game-front-id.png")
            Image.fromarray((np.clip(beauty, 0, 1) * 255).astype(np.uint8)).save(b)
            Image.fromarray((ids * 255).astype(np.uint8)).save(i)
            return gap_measures(b, i)

    def test_an_even_closed_mass_has_neither(self):
        m = self.measure(*head()[:2])
        self.assertEqual(m["crevice"], 0.0)
        self.assertLess(m["outline_ragged"], 0.005)

    def test_dark_lines_between_locks_are_crevices(self):
        beauty, ids, hair = head()
        lines = np.zeros_like(hair)
        lines[:, 60:200:20] = True
        lines[:, 61:200:20] = True
        beauty[hair & lines] = 0.05
        m = self.measure(beauty, ids)
        self.assertGreater(m["crevice"], 0.05)

    def test_a_side_in_shade_is_not_a_crevice(self):
        # A smooth falloff across the head is lighting, not a gap.
        beauty, ids, hair = head()
        ramp = np.linspace(0.9, 0.15, SIZE)[None, :].repeat(SIZE, 0)
        beauty[hair] = ramp[hair][:, None]
        self.assertLess(self.measure(beauty, ids)["crevice"], 0.01)

    def test_spiky_tips_make_a_ragged_crown(self):
        # Lock tips gathered into points with the sky between them.
        beauty, ids, hair = head()
        notch = np.zeros_like(hair)
        for x in range(60, 200, 16):
            notch[18:40, x:x + 6] = True
        ids[notch] = 0.0
        beauty[notch] = 0.35
        even = self.measure(*head()[:2])["outline_ragged"]
        self.assertGreater(self.measure(beauty, ids)["outline_ragged"], even + 0.01)

    def test_a_lone_flyaway_does_not_count(self):
        beauty, ids, hair = head()
        ids[5:20, 128, 0] = 0.3   # a thin, part-covered strand standing off the crown
        even = self.measure(*head()[:2])["outline_ragged"]
        self.assertAlmostEqual(self.measure(beauty, ids)["outline_ragged"], even, places=3)


if __name__ == "__main__":
    unittest.main()
