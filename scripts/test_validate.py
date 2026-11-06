"""Tests for the citation gate in validate.py. Run: python -m unittest discover scripts"""
import json, sys, tempfile, unittest
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


if __name__ == "__main__":
    unittest.main()