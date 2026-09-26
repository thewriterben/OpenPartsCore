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


FEATURE_KINDS = {"board", "connector", "switch", "card_slot", "antenna", "optic", "component"}
# Kinds something has to reach: a plug, a card, a finger, a lens's view.
ACCESS_KINDS = {"connector", "switch", "card_slot", "antenna", "optic"}
AXES = {"+x", "-x", "+y", "-y", "+z", "-z"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _vec3(v) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(_num(c) for c in v)


def check_features(feat) -> list[str]:
    """features is optional; when present it is sourced, revisioned and complete (ADR-0007).

    The rules that matter are the ones a consumer cannot recover from later:
    which revision and which model file the positions came from, what the
    items do not cover, and - for anything a plug or finger must reach -
    whether the free volume is known. Unknown is allowed and spelled null;
    missing is not, because missing reads as "nothing to reach".
    """
    if feat is None:
        return []
    if not isinstance(feat, dict):
        return ["features must be an object"]
    errs = []
    extra = set(feat) - {"source", "frame", "not_modelled", "items"}
    if extra:
        errs.append(f"features has unknown keys {sorted(extra)}")
    src = feat.get("source")
    if not isinstance(src, dict):
        errs.append("features.source missing - features carry their own source (ADR-0007)")
    else:
        if not str(src.get("citation", "")).strip():
            errs.append("features.source has no citation")
        if not SHA256_RE.match(str(src.get("model_sha256", ""))):
            errs.append("features.source.model_sha256 must be the 64-hex sha256 of the model the positions came from")
        if not str(src.get("revision", "")).strip():
            errs.append("features.source.revision missing - positions belong to one hardware revision")
        extra = set(src) - {"citation", "model_sha256", "revision", "url", "retrieved"}
        if extra:
            errs.append(f"features.source has unknown keys {sorted(extra)}")
    if not str(feat.get("frame", "")).strip():
        errs.append("features.frame missing - coordinates without a stated origin and axes mean nothing")
    nm = feat.get("not_modelled")
    if not isinstance(nm, list) or not all(isinstance(s, str) and s.strip() for s in nm):
        errs.append("features.not_modelled must be a list of non-empty strings (empty list if the items are complete)")
    items = feat.get("items")
    if not isinstance(items, list) or not items:
        errs.append("features.items must be a non-empty list")
        return errs
    seen: set[str] = set()
    for i, it in enumerate(items):
        errs.extend(_check_item(i, it, seen))
    return errs


def _check_item(i: int, it, seen: set[str]) -> list[str]:
    if not isinstance(it, dict):
        return [f"features.items[{i}] must be an object"]
    errs = []
    fid = it.get("id")
    where = f"features.items[{i}]" + (f" '{fid}'" if isinstance(fid, str) else "")
    if not isinstance(fid, str) or not fid.strip():
        errs.append(f"{where}: id missing")
    elif fid in seen:
        errs.append(f"{where}: duplicate id")
    else:
        seen.add(fid)
    kind = it.get("kind")
    if kind not in FEATURE_KINDS:
        errs.append(f"{where}: kind must be one of {sorted(FEATURE_KINDS)}")
    if not str(it.get("source", "")).strip():
        errs.append(f"{where}: no source - say which STEP solid or which measurement")
    extra = set(it) - {"id", "kind", "box_mm", "cylinder_mm", "source", "access"}
    if extra:
        errs.append(f"{where}: unknown keys {sorted(extra)}")

    has_box, has_cyl = "box_mm" in it, "cylinder_mm" in it
    if has_box == has_cyl:
        errs.append(f"{where}: exactly one of box_mm or cylinder_mm")
    if has_box:
        box = it["box_mm"]
        if not isinstance(box, dict) or not _vec3(box.get("min_mm")) or not _vec3(box.get("max_mm")):
            errs.append(f"{where}: box_mm needs min_mm and max_mm, three numbers each")
        elif any(box["min_mm"][k] >= box["max_mm"][k] for k in range(3)):
            errs.append(f"{where}: box_mm min_mm must be below max_mm on every axis")
        elif set(box) - {"min_mm", "max_mm"}:
            errs.append(f"{where}: box_mm has unknown keys")
    if has_cyl:
        cyl = it["cylinder_mm"]
        ok = (isinstance(cyl, dict) and cyl.get("axis") in AXES and _vec3(cyl.get("base_mm"))
              and _num(cyl.get("length_mm")) and cyl["length_mm"] > 0
              and _num(cyl.get("diameter_mm")) and cyl["diameter_mm"] > 0
              and not set(cyl) - {"axis", "base_mm", "length_mm", "diameter_mm"})
        if not ok:
            errs.append(f"{where}: cylinder_mm needs axis (±x/±y/±z), base_mm, positive length_mm and diameter_mm, nothing else")

    acc = it.get("access")
    if kind in ACCESS_KINDS and acc is None:
        errs.append(f"{where}: a {kind} must declare access (direction/depth_mm may be null = unknown, but not absent)")
    if acc is not None:
        if not isinstance(acc, dict):
            errs.append(f"{where}: access must be an object")
        else:
            if "direction" not in acc or (acc["direction"] is not None and acc["direction"] not in AXES):
                errs.append(f"{where}: access.direction must be ±x/±y/±z or null")
            d = acc.get("depth_mm", "missing")
            if d == "missing" or (d is not None and (not _num(d) or d <= 0)):
                errs.append(f"{where}: access.depth_mm must be a positive number or null")
            sec = acc.get("section_mm")
            if sec is not None and not (isinstance(sec, list) and len(sec) == 2 and all(_num(s) and s > 0 for s in sec)):
                errs.append(f"{where}: access.section_mm must be two positive numbers when present")
            if not str(acc.get("source", "")).strip():
                errs.append(f"{where}: access has no source")
            if set(acc) - {"direction", "depth_mm", "section_mm", "source"}:
                errs.append(f"{where}: access has unknown keys")
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
    errs.extend(check_features(e.get("features")))
    # The schema says additionalProperties:false at the top level; this is
    # where that is enforced, since a new key is exactly how a fact arrives
    # without its own source.
    extra = set(e) - {"schema_version", "id", "namespace", "name", "description",
                      "source", "attributes", "envelope_mm", "features", "links"}
    if extra:
        errs.append(f"unknown top-level keys {sorted(extra)} - a new fact needs a schema field and an ADR")
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
