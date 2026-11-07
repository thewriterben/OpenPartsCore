#!/usr/bin/env python3
"""Ingest Oh-Ben-Claw's registry.json into the canonical namespaces.

Idempotent: rerunning with an unchanged upstream rewrites nothing.

Every entry cites the upstream file at the commit it was read from, in the
validator's ``repo:`` form (``repo:<owner>/<name>@<sha>:registry/registry.json``),
so strict citation mode holds for the ingested namespaces. The registry path
must therefore sit in a clean git checkout whose HEAD is on a remote branch:
a citation of a dirty tree or an unpushed commit names something nobody else
can open, and the script refuses rather than write it.

The upstream file is a list of *USB identity rows*, not of boards: 69 rows
cover 66 board models and 44 distinct VID/PID pairs. Neither is a key -- one
board can enumerate through several USB-UART bridges, and one bridge chip
serves many boards (ADR-0004). This script groups rows by board name and
carries the identities as a list, which is the canonical shape.

Usage:
    python scripts/ingest_obc.py <path-to-oh-ben-claw>/registry/registry.json
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class UpstreamNotCitable(RuntimeError):
    """The registry file cannot be cited by commit; the message says why."""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


def upstream_citation(registry_path: Path) -> str:
    """``repo:<owner>/<name>@<sha>:<path>`` for the checkout holding ``registry_path``.

    Refuses (UpstreamNotCitable) when the file is not inside a git checkout, has
    uncommitted changes, or HEAD is on no remote branch: each would cite a
    state of the file that the citation cannot lead a reader back to.
    """
    registry_path = registry_path.resolve()
    try:
        root = Path(_git(registry_path.parent, "rev-parse", "--show-toplevel"))
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise UpstreamNotCitable(f"{registry_path} is not inside a git checkout") from exc
    rel = registry_path.relative_to(root.resolve()).as_posix()
    if _git(root, "status", "--porcelain", "--", rel):
        raise UpstreamNotCitable(f"{rel} has uncommitted changes in {root}; commit and push them first")
    sha = _git(root, "rev-parse", "HEAD")
    if not _git(root, "branch", "-r", "--contains", sha):
        raise UpstreamNotCitable(f"commit {sha[:12]} in {root} is on no remote branch; push it first")
    url = _git(root, "remote", "get-url", "origin")
    m = re.search(r"[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$", url)
    if not m:
        raise UpstreamNotCitable(f"cannot read owner/name from origin url {url!r}")
    return f"repo:{m.group(1)}/{m.group(2)}@{sha}:{rel}"


def slug(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "._-") else "-" for c in name.lower())


# Fields the ingest does not own. Upstream has no dimensions, no features and
# no links, so anything under these keys was added here, by hand, with its own
# citation (ADR-0006, ADR-0007) -- a re-ingest that rewrote the file from
# upstream alone would delete it silently, which is how a cited envelope would
# vanish between two runs that both reported "unchanged".
PRESERVED_KEYS = ("envelope_mm", "features", "links")


def write_entry(path: Path, entry: dict) -> bool:
    """Write only if content differs; returns True when the file changed.

    Keys in PRESERVED_KEYS are carried over from the existing file when
    present: upstream cannot supply them, so the ingest must not remove them.
    """
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        for key in PRESERVED_KEYS:
            if key in existing and existing[key]:
                entry[key] = existing[key]
        # `retrieved` says when the upstream facts were last read *and found
        # different*. Stamping today's date onto an unchanged entry rewrote
        # every file on the first run of each day, which made "idempotent"
        # true only within a day and buried real changes in a 100-file diff.
        # The same holds for the cited commit: when the facts an entry carries
        # are unchanged, the commit they were last read from still holds them,
        # so the citation stays put rather than moving with every upstream
        # commit that touched something else. A free-text citation is never
        # kept: it is exactly what the repo: form replaces.
        old_source = existing.get("source") or {}
        old_retrieved = old_source.get("retrieved")
        old_citation = old_source.get("citation", "")
        if old_retrieved:
            keep = {"retrieved": old_retrieved}
            if old_citation.startswith("repo:"):
                keep["citation"] = old_citation
            probe = dict(entry, source=dict(entry["source"], **keep))
            probe_tail = {k: probe.pop(k) for k in PRESERVED_KEYS if k in probe}
            probe.update(probe_tail)
            if probe == existing:
                entry["source"].update(keep)
    # Stable key order regardless of which side supplied a field, so a
    # preserved envelope does not make the next run report a change.
    tail = {k: entry.pop(k) for k in PRESERVED_KEYS if k in entry}
    entry.update(tail)
    text = json.dumps(entry, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def ingest(registry_path: Path, citation: str | None = None) -> tuple[int, int, int]:
    citation = citation or upstream_citation(registry_path)
    upstream = json.loads(registry_path.read_text(encoding="utf-8"))
    schema_version = upstream.get("schema_version", "unknown")
    retrieved = date.today().isoformat()

    # --- boards: group identity rows into one entry per board model ---
    boards: OrderedDict[str, dict] = OrderedDict()
    for row in upstream.get("boards", []):
        board = boards.setdefault(
            row["name"],
            {
                "usb_ids": [],
                "capabilities": [],
                "connectors": [],
                "vendor": row.get("vendor"),
                "ecosystem": row.get("ecosystem"),
                "transport": row.get("transport"),
            },
        )
        board["usb_ids"].append(
            {
                "vid": row["vid"],
                "pid": row["pid"],
                "architecture": row.get("architecture"),
            }
        )
        for key in ("capabilities", "connectors"):
            for value in row.get(key, []):
                if value not in board[key]:
                    board[key].append(value)

    changed = 0
    for name, board in boards.items():
        board["usb_ids"].sort(key=lambda o: (o["vid"], o["pid"]))
        board["capabilities"].sort()
        board["connectors"].sort()
        entry = {
            "schema_version": 0,
            "id": f"boards/{slug(name)}",
            "namespace": "boards",
            "name": name,
            "description": board["usb_ids"][0]["architecture"] or name,
            "source": {
                "citation": citation,
                "retrieved": retrieved,
                "upstream_schema_version": schema_version,
            },
            "attributes": board,
            "links": {},
        }
        if write_entry(ROOT / "data" / "boards" / f"{slug(name)}.json", entry):
            changed += 1

    # --- accessories: modules and sensors land in the electronic namespace ---
    accessories = upstream.get("accessories", [])
    for row in accessories:
        entry = {
            "schema_version": 0,
            "id": f"electronic/{slug(row['name'])}",
            "namespace": "electronic",
            "name": row["name"],
            "description": row.get("description", row["name"]),
            "source": {
                "citation": citation,
                "retrieved": retrieved,
                "upstream_schema_version": schema_version,
            },
            "attributes": {
                "bus": row.get("bus"),
                "default_i2c_addr": row.get("default_i2c_addr"),
                "capabilities": sorted(row.get("capabilities", [])),
                "compatible_boards": sorted(row.get("compatible_boards", [])),
                "connector": row.get("connector"),
            },
            "links": {},
        }
        if write_entry(ROOT / "data" / "electronic" / f"{slug(row['name'])}.json", entry):
            changed += 1

    return len(boards), len(accessories), changed


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    registry_path = Path(sys.argv[1])
    if not registry_path.exists():
        print(f"upstream registry not found: {registry_path}", file=sys.stderr)
        return 1

    try:
        boards, accessories, changed = ingest(registry_path)
    except UpstreamNotCitable as exc:
        print(f"refusing to ingest: {exc}", file=sys.stderr)
        return 1
    print(
        f"{boards} board model(s), {accessories} accessory/accessories ingested; "
        f"{changed} file(s) written or updated."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
