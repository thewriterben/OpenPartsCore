"""Tests for the upstream citation ingest_obc.py writes. Run: python -m unittest discover scripts"""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_obc
import validate

REGISTRY = {"schema_version": 1, "boards": [
    {"name": "Test Board", "vid": 1, "pid": 2, "architecture": "arch", "vendor": "v", "ecosystem": "e", "transport": "usb"},
], "accessories": []}


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


class UpstreamCitation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "obc"
        (self.root / "registry").mkdir(parents=True)
        self.registry = self.root / "registry" / "registry.json"
        self.registry.write_text(json.dumps(REGISTRY), encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "root")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "registry")
        git(self.root, "remote", "add", "origin", "https://github.com/owner/Repo-Name.git")
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cites_owner_name_commit_and_path_in_the_strict_repo_form(self):
        sha = git(self.root, "rev-parse", "HEAD")
        citation = ingest_obc.upstream_citation(self.registry)
        self.assertEqual(citation, f"repo:owner/Repo-Name@{sha}:registry/registry.json")
        self.assertTrue(validate.CITATION_FORMS["repo"].match(citation))

    def test_refuses_uncommitted_changes(self):
        self.registry.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ingest_obc.UpstreamNotCitable, "uncommitted changes"):
            ingest_obc.upstream_citation(self.registry)

    def test_refuses_a_commit_on_no_remote_branch(self):
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "local only")
        with self.assertRaisesRegex(ingest_obc.UpstreamNotCitable, "no remote branch"):
            ingest_obc.upstream_citation(self.registry)

    def test_refuses_a_file_outside_any_checkout(self):
        loose = Path(self._tmp.name) / "registry.json"
        loose.write_text("{}", encoding="utf-8")
        with self.assertRaises(ingest_obc.UpstreamNotCitable):
            ingest_obc.upstream_citation(loose)


class WriteEntry(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "t.json"

    def tearDown(self):
        self._tmp.cleanup()

    def entry(self, citation, retrieved="2026-11-06", vid=1):
        return {"schema_version": 0, "id": "boards/t", "namespace": "boards", "name": "t", "description": "t",
                "source": {"citation": citation, "retrieved": retrieved, "upstream_schema_version": 1},
                "attributes": {"usb_ids": [{"vid": vid, "pid": 2}]}, "links": {}}

    def test_unchanged_facts_keep_the_commit_they_were_read_from(self):
        old = "repo:o/r@" + "a" * 40 + ":registry/registry.json"
        self.assertTrue(ingest_obc.write_entry(self.path, self.entry(old)))
        new = "repo:o/r@" + "b" * 40 + ":registry/registry.json"
        self.assertFalse(ingest_obc.write_entry(self.path, self.entry(new, retrieved="2026-11-07")))
        self.assertEqual(json.loads(self.path.read_text())["source"], {"citation": old, "retrieved": "2026-11-06", "upstream_schema_version": 1})

    def test_changed_facts_move_to_the_new_commit_and_date(self):
        old = "repo:o/r@" + "a" * 40 + ":registry/registry.json"
        ingest_obc.write_entry(self.path, self.entry(old))
        new = "repo:o/r@" + "b" * 40 + ":registry/registry.json"
        self.assertTrue(ingest_obc.write_entry(self.path, self.entry(new, retrieved="2026-11-07", vid=9)))
        self.assertEqual(json.loads(self.path.read_text())["source"]["citation"], new)
        self.assertEqual(json.loads(self.path.read_text())["source"]["retrieved"], "2026-11-07")

    def test_a_free_text_citation_is_replaced_and_dated_even_when_facts_are_unchanged(self):
        ingest_obc.write_entry(self.path, self.entry("Oh-Ben-Claw registry/registry.json (generated)"))
        new = "repo:o/r@" + "b" * 40 + ":registry/registry.json"
        self.assertTrue(ingest_obc.write_entry(self.path, self.entry(new, retrieved="2026-11-07")))
        # The facts were re-read from the cited commit on the new date; the old date belonged to a citation that is gone.
        self.assertEqual(json.loads(self.path.read_text())["source"], {"citation": new, "retrieved": "2026-11-07", "upstream_schema_version": 1})


if __name__ == "__main__":
    unittest.main()
