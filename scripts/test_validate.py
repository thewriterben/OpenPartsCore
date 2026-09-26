#!/usr/bin/env python3
"""Tests for the rules in validate.py that a consumer relies on without re-checking.

    python scripts/test_validate.py

Stdlib unittest, like everything else here. Each case is one of the ways a
`features` block could look sourced and still mislead a clearance check
(ADR-0007): no revision, a connector with no access declaration at all
(which reads as "nothing to reach"), a duplicate id, an inside-out box.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402

GOOD = {
    "source": {"citation": "test fixture - synthetic", "model_sha256": "0" * 64, "revision": "T1"},
    "frame": "synthetic frame",
    "not_modelled": [],
    "items": [
        {"id": "Board", "kind": "board", "source": "synthetic",
         "box_mm": {"min_mm": [0, 0, 0], "max_mm": [10, 20, 1]}},
        {"id": "USB1", "kind": "connector", "source": "synthetic",
         "box_mm": {"min_mm": [3, -1, 1], "max_mm": [7, 4, 4]},
         "access": {"direction": "-y", "depth_mm": None, "source": "synthetic"}},
        {"id": "lens", "kind": "optic", "source": "synthetic",
         "cylinder_mm": {"axis": "-z", "base_mm": [5, 10, 0], "length_mm": 5, "diameter_mm": 4},
         "access": {"direction": None, "depth_mm": None, "source": "synthetic"}},
    ],
}


def errs(mutate):
    f = copy.deepcopy(GOOD)
    mutate(f)
    return validate.check_features(f)


class FeatureRules(unittest.TestCase):
    def test_the_good_fixture_is_valid(self):
        self.assertEqual(validate.check_features(GOOD), [])

    def test_absent_features_is_fine(self):
        self.assertEqual(validate.check_features(None), [])

    def test_revision_is_required(self):
        self.assertTrue(any("revision" in e for e in errs(lambda f: f["source"].pop("revision"))))

    def test_model_hash_must_be_a_sha256(self):
        self.assertTrue(any("model_sha256" in e for e in errs(
            lambda f: f["source"].__setitem__("model_sha256", "abc"))))

    def test_not_modelled_is_required_even_when_empty(self):
        self.assertTrue(any("not_modelled" in e for e in errs(lambda f: f.pop("not_modelled"))))

    def test_a_connector_without_access_is_rejected(self):
        # The failure this schema exists for: silence read as clearance.
        self.assertTrue(any("must declare access" in e for e in errs(
            lambda f: f["items"][1].pop("access"))))

    def test_unknown_access_is_spelled_null_and_accepted(self):
        self.assertEqual(errs(lambda f: None), [])

    def test_zero_depth_is_not_unknown(self):
        self.assertTrue(any("depth_mm" in e for e in errs(
            lambda f: f["items"][1]["access"].__setitem__("depth_mm", 0))))

    def test_duplicate_ids_are_rejected(self):
        self.assertTrue(any("duplicate" in e for e in errs(
            lambda f: f["items"][2].__setitem__("id", "USB1"))))

    def test_an_inside_out_box_is_rejected(self):
        self.assertTrue(any("below max_mm" in e for e in errs(
            lambda f: f["items"][0]["box_mm"].__setitem__("min_mm", [0, 30, 0]))))

    def test_exactly_one_shape(self):
        def both(f):
            f["items"][0]["cylinder_mm"] = copy.deepcopy(GOOD["items"][2]["cylinder_mm"])
        self.assertTrue(any("exactly one" in e for e in errs(both)))

    def test_cylinders_are_axis_aligned(self):
        self.assertTrue(any("cylinder_mm" in e for e in errs(
            lambda f: f["items"][2]["cylinder_mm"].__setitem__("axis", "diagonal"))))


if __name__ == "__main__":
    unittest.main()
