#!/usr/bin/env python3
"""Ingest Oh-Ben-Claw's registry.json into the canonical namespaces.

Idempotent: rerunning with an unchanged upstream rewrites nothing.

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
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = "Oh-Ben-Claw registry/registry.json (generated from src/peripherals/registry.rs)"


def slug(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "._-") else "-" for c in name.lower())


def write_entry(path: Path, entry: dict) -> bool:
    """Write only if content differs; returns True when the file changed."""
    text = json.dumps(entry, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def ingest(registry_path: Path) -> tuple[int, int, int]:
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
                "citation": UPSTREAM,
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
                "citation": UPSTREAM,
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

    boards, accessories, changed = ingest(registry_path)
    print(
        f"{boards} board model(s), {accessories} accessory/accessories ingested; "
        f"{changed} file(s) written or updated."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
