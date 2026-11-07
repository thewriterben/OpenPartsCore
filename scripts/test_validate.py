#!/usr/bin/env python3
"""Tests for validate.py: the citation gate, the namespace schemas, and the
feature rules a consumer relies on without re-checking.

    python -m unittest discover scripts

Stdlib unittest, like everything else here (jsonschema is needed only for
the namespace schemas). The FeatureRules cases are the ways a `features`
block could look sourced and still mislead a clearance check (ADR-0007): no
revision, a connector with no access declaration at all (which reads as
"nothing to reach"), a duplicate id, an inside-out box.
"""
import copy, json, sys, tempfile, unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402

VAULT = "vault:sha256:" + "ab" * 32
BLOCK_ID = "20260106123456-abcdefg"


def entry(citation, attributes=None):
    e = {"schema_version": 0, "id": "boards/t", "namespace": "boards", "name": "t",
         "source": {"citation": citation}}
    if attributes is not None:
        e["attributes"] = attributes
    return e


def run(e, strict=False):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / e["namespace"] / "t.json"
        p.parent.mkdir()
        p.write_text(json.dumps(e), encoding="utf-8")
        return validate.check(p, strict=strict)


class CitationGate(unittest.TestCase):
    def test_siyuan_block_id_in_citation_fails(self):
        errs = run(entry(f"notes {BLOCK_ID}"))
        self.assertTrue(any("SiYuan block id" in x for x in errs), errs)

    def test_siyuan_url_in_attributes_fails(self):
        errs = run(entry(VAULT, {"deep": [{"link": "siyuan://blocks/" + BLOCK_ID}]}))
        self.assertTrue(any("siyuan URL" in x and "attributes" in x for x in errs), errs)

    def test_kernel_address_and_sy_path_fail(self):
        self.assertTrue(run(entry("http://127.0.0.1:6806/api/block/get")))
        self.assertTrue(run(entry("data/20260106123456-abcdefg.sy")))

    def test_vault_citation_passes_in_both_modes(self):
        self.assertEqual(run(entry(VAULT)), [])
        self.assertEqual(run(entry(VAULT + "#page=2"), strict=True), [])

    def test_free_text_passes_by_default_and_fails_strict(self):
        e = entry("Espressif ESP32-S3 datasheet v1.6")
        self.assertEqual(run(e), [])
        self.assertTrue(any("free text" in x for x in run(e, strict=True)))

    def test_empty_citation_still_fails(self):
        self.assertTrue(run(entry("  ")))

    def test_strict_checks_nested_source_strings(self):
        e = entry(VAULT, {"tds": {"source": "some free text"}})
        self.assertEqual(run(e), [])
        self.assertTrue(run(e, strict=True))

    def test_feature_item_sources_are_locators_not_citations(self):
        # ADR-0008: items[].source and access.source point inside the model
        # that features.source cites; strict asks a form of features.source only.
        f = copy.deepcopy(GOOD)
        f["source"]["citation"] = VAULT
        e = entry(VAULT)
        e["features"] = f
        self.assertEqual(run(e, strict=True), [])
        f["source"]["citation"] = "free text"
        self.assertTrue(any("$.features.source.citation is free text" in x for x in run(e, strict=True)))
        f["source"]["citation"] = VAULT
        f["items"][1]["access"]["source"] = "see siyuan://blocks/" + BLOCK_ID
        self.assertTrue(any("SiYuan" in x for x in run(e, strict=True)))

    def test_every_committed_entry_passes_strict_mode(self):
        """CI runs bare --strict: no namespace may regress to free-text citations."""
        data = Path(__file__).resolve().parents[1] / "data"
        for p in sorted(data.glob("*/*.json")):
            self.assertEqual(validate.check(p, strict=True), [], p.name)

    def test_note_beside_a_citation_is_not_a_citation(self):
        e = entry(VAULT)
        e["source"]["note"] = "how the cited bytes yield the values"
        e["envelope_mm"] = {"x": 1, "y": 2, "z": 3, "source": {"citation": VAULT, "note": "measured"}}
        self.assertEqual(run(e, strict=True), [])
        e["envelope_mm"]["source"]["citation"] = "measured by hand"
        self.assertTrue(any("envelope_mm" in x and "free text" in x for x in run(e, strict=True)))

    def test_every_committed_entry_passes_default_mode(self):
        self.assertEqual(validate.main([]), 0)


MATERIAL = {
    "identity": {"vendor": "V", "product": "P", "polymer": "PLA", "form": "filament", "diameter_mm": 1.75,
                 "source": VAULT},
    "normalised": {"note": "n", "source": VAULT, "density_g_cm3": {"value": 1.24, "page": 1},
                   "nozzle_temp_c": {"min": 190, "max": 230, "basis": "RFID tag"}, "shrinkage_pct": None},
    "review": {"status": "proposed", "flags": []},
}


def material(attributes):
    e = entry(VAULT, attributes)
    e.update(id="material/t", namespace="material")
    return e


class NamespaceSchema(unittest.TestCase):
    """schema/material.schema.json checks `attributes` in material/ (ADR-0007)."""

    def test_minimal_material_entry_passes(self):
        self.assertEqual(run(material(MATERIAL), strict=True), [])

    def test_missing_review_block_fails(self):
        errs = run(material({k: v for k, v in MATERIAL.items() if k != "review"}))
        self.assertTrue(any("attributes: 'review' is a required property" in x for x in errs), errs)

    def test_unknown_block_and_bad_status_fail(self):
        a = json.loads(json.dumps(MATERIAL))
        a["extra"] = {}
        a["review"]["status"] = "fine"
        errs = run(material(a))
        self.assertTrue(any(x.startswith("attributes: Additional properties") and "extra" in x for x in errs), errs)
        self.assertTrue(any(x.startswith("attributes.review.status:") for x in errs), errs)

    def test_normalised_number_needs_a_unit_key_and_a_page_or_basis(self):
        a = json.loads(json.dumps(MATERIAL))
        a["normalised"]["density"] = {"value": 1.24, "page": 1}
        a["normalised"]["bed_temp_c"] = {"value": 60}
        a["normalised"]["sample_print"] = {"nozzle_c": 220, "page": 1}
        errs = run(material(a))
        self.assertTrue(any("attributes.normalised:" in x and "density" in x for x in errs), errs)
        self.assertTrue(any(x.startswith("attributes.normalised.bed_temp_c:") for x in errs), errs)
        self.assertTrue(any("sample_print" in x for x in errs), errs)
        self.assertNotIn("sample_print_nozzle_c", " ".join(run(material(MATERIAL))))

    def test_missing_jsonschema_package_is_an_error_not_a_skip(self):
        with mock.patch.dict(sys.modules, {"jsonschema": None}):
            errs = run(material(MATERIAL))
        self.assertTrue(any("jsonschema package is not installed" in x for x in errs), errs)

    def test_namespaces_without_a_schema_keep_free_attributes(self):
        self.assertEqual(run(entry(VAULT, {"anything": [1, {"goes": None}]})), [])


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
