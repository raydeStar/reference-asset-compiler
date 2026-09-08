"""Exercise the actual editor helper math without loading Unreal or a GPU."""
import ast
import math
from pathlib import Path
import unittest


class RetargetMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'scripts/ue5/build_workshop_rig_repair.py'
        tree = ast.parse(path.read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'qmul', 'qi'}]
        cls.helpers = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), cls.helpers)

    def assertQuaternionClose(self, actual, expected):
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=10)

    def test_inverse_cancels_non_unit_quaternion(self):
        q = (.1, -.2, .3, .7)
        self.assertQuaternionClose(self.helpers['qmul'](q, self.helpers['qi'](q)), (0, 0, 0, 1))

    def test_parent_reference_offset_reconstructs_desired_rotation(self):
        multiply, inverse = self.helpers['qmul'], self.helpers['qi']
        parent = (0, math.sin(.3), 0, math.cos(.3))
        reference = (math.sin(.4), 0, 0, math.cos(.4))
        desired = (0, 0, math.sin(.6), math.cos(.6))
        offset = multiply(inverse(reference), multiply(inverse(parent), desired))
        self.assertQuaternionClose(multiply(parent, multiply(reference, offset)), desired)

    def test_rotation_order_is_not_commutative(self):
        multiply = self.helpers['qmul']
        a, b = (.6, 0, 0, .8), (0, .6, 0, .8)
        self.assertNotEqual(multiply(a, b), multiply(b, a))


if __name__ == '__main__':
    unittest.main()
