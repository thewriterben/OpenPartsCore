"""Tests for the citation gate in validate.py. Run: python -m unittest discover scripts"""
import json, sys, tempfile, unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate

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


if __name__ == "__main__":
    unittest.main()