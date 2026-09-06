#!/usr/bin/env python3
"""Validate all entries in data/ against the structural rules of schema v0.

Stdlib only (no jsonschema dependency): checks required fields, id/namespace
agreement, citation presence, and the unit-suffix convention for length.
The JSON Schema in schema/ remains the authoritative definition for tooling
that can consume it.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMESPACES = {"boards", "electronic", "mechanical", "material"}
ID_RE = re.compile(r"^(boards|electronic|mechanical|material)/[a-z0-9][a-z0-9._-]*$")

def check_envelope(env) -> list[str]:
    """envelope_mm is optional; when present it is complete, positive and cited.

    It carries its own source (ADR-0006): the entry-level citation names where
    the identity came from, which for every ingested board is a registry that
    holds no dimensions. A number with no source of its own is a number that
    inherited a citation it is not covered by.
    """
    if env is None:
        return []
    errs = []
    if not isinstance(env, dict):
        return ["envelope_mm must be an object"]
    for axis in ("x", "y", "z"):
        v = env.get(axis)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(f"envelope_mm.{axis} missing or not a number — absent means unknown, never zero")
        elif v <= 0:
            errs.append(f"envelope_mm.{axis} must be positive")
    tol = env.get("tolerance_mm")
    if tol is not None and (not isinstance(tol, (int, float)) or isinstance(tol, bool) or tol <= 0):
        errs.append("envelope_mm.tolerance_mm must be a positive number when present")
    if not str((env.get("source") or {}).get("citation", "")).strip():
        errs.append("envelope_mm has no citation of its own — the entry-level source does not cover it")
    extra = set(env) - {"x", "y", "z", "tolerance_mm", "source"}
    if extra:
        errs.append(f"envelope_mm has unknown keys {sorted(extra)}")
    return errs


def check(path: Path) -> list[str]:
    errs = []
    try:
        e = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        return [f"invalid JSON: {ex}"]
    for field in ("schema_version", "id", "namespace", "name", "source"):
        if field not in e:
            errs.append(f"missing required field '{field}'")
    if errs:
        return errs
    if e["schema_version"] != 0:
        errs.append(f"schema_version {e['schema_version']} != 0")
    if not ID_RE.match(e["id"]):
        errs.append(f"bad id '{e['id']}'")
    if e["namespace"] not in NAMESPACES:
        errs.append(f"bad namespace '{e['namespace']}'")
    elif not e["id"].startswith(e["namespace"] + "/"):
        errs.append("id prefix does not match namespace")
    if e["namespace"] != path.parent.name:
        errs.append(f"file is in data/{path.parent.name}/ but namespace is '{e['namespace']}'")
    if not str(e.get("source", {}).get("citation", "")).strip():
        errs.append("empty citation — uncited entries are invalid")
    errs.extend(check_envelope(e.get("envelope_mm")))
    # unit-suffix convention: numeric leaf keys about length must end in _mm
    def walk(obj, crumb=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    lk = k.lower()
                    if any(w in lk for w in ("length", "width", "height", "depth", "diameter", "pitch")) and not lk.endswith("_mm"):
                        errs.append(f"length-like numeric field '{crumb}{k}' must end in _mm")
                walk(v, crumb + k + ".")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{crumb}{i}.")
    walk(e)
    return errs

def main() -> int:
    data = ROOT / "data"
    files = sorted(data.rglob("*.json"))
    if not files:
        print("no entries found under data/", file=sys.stderr)
        return 1
    failed = 0
    for f in files:
        errs = check(f)
        if errs:
            failed += 1
            for e in errs:
                print(f"FAIL {f.relative_to(ROOT)}: {e}")
    print(f"{len(files) - failed}/{len(files)} entries valid")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
