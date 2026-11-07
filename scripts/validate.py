#!/usr/bin/env python3
"""Validate all entries in data/ against the structural rules of schema v0.

The structural rules are stdlib only: required fields, id/namespace agreement,
citation presence, and the unit-suffix convention for length. The JSON Schema in
schema/ remains the authoritative definition for tooling that can consume it.

Namespace schemas (ADR-0007): when schema/<namespace>.schema.json exists, every
entry's `attributes` is validated against it with the jsonschema package. Only
`material` has one so far. Its absence is an error, not a skip, so CI cannot
pass by not looking.

Citation gate (OpenKnowledgeCore ADR-0001): SiYuan is a projection, never a
source. In every run, any string anywhere in an entry that references SiYuan is
an error. With --strict, every `source` citation must also use one of the
accepted forms. Free-text citations (the `boards` entries) pass by default.
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMESPACES = {"boards", "electronic", "mechanical", "material"}
ID_RE = re.compile(r"^(boards|electronic|mechanical|material)/[a-z0-9][a-z0-9._-]*$")

# --- SiYuan rejection and strict citation forms -----------------------------
# Vendored from OpenKnowledgeCore okc/validate.py (ADR-0001), stdlib only. Keep
# the patterns in step with that file; this one is self-contained on purpose so
# CI here needs nothing from another repository.

SIYUAN_REJECTIONS = [
    ("siyuan URL", re.compile(r"siyuan://", re.IGNORECASE)),
    ("SiYuan block id", re.compile(r"\b\d{14}-[a-z0-9]{7}\b")),
    ("SiYuan kernel address", re.compile(r"(localhost|127\.0\.0\.1|\[::1\]):6806\b")),
    ("SiYuan .sy file path", re.compile(r"(^|[\\/ ])[^\s\\/]+\.sy(\b|$)")),
]

# Accepted citation forms, enforced only under --strict.
CITATION_FORMS = {
    "vault": re.compile(r"^vault:sha256:[0-9a-f]{64}(#page=\d+)?$"),
    "repo": re.compile(r"^repo:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{7,40}:[^\s:][^\s]*$"),
    "ledger": re.compile(r"^ledger:[a-z0-9_-]+:[A-Za-z0-9_.-]+$"),
    "doi": re.compile(r"^doi:10\.\d{4,9}/\S+$"),
    "arxiv": re.compile(r"^arxiv:\d{4}\.\d{4,5}(v\d+)?$"),
    "standard": re.compile(r"^standard:[A-Z][A-Z0-9/ -]*? [0-9][0-9.-]*:(19|20)\d{2}$"),
}


def siyuan_reference(text: str):
    """Label of the first SiYuan pattern found in text, or None."""
    for label, pattern in SIYUAN_REJECTIONS:
        if pattern.search(text):
            return label
    return None


def iter_strings(obj, crumb="$"):
    """Yield (json_path, string) for every string value and key in a document."""
    if isinstance(obj, str):
        yield crumb, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_strings(k, f"{crumb}.<key {k!r}>")
            yield from iter_strings(v, f"{crumb}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_strings(v, f"{crumb}[{i}]")


def iter_citations(obj, crumb="$"):
    """Yield (json_path, citation) for every `source` key: a bare string, or the
    `citation` of a {citation, retrieved} object, at any depth."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{crumb}.{k}"
            if k == "source":
                cit = v.get("citation") if isinstance(v, dict) else v
                if isinstance(cit, str):
                    yield (path + ".citation" if isinstance(v, dict) else path), cit
            yield from iter_citations(v, path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_citations(v, f"{crumb}[{i}]")


def check_citations(e, strict: bool) -> list[str]:
    errs = []
    for crumb, text in iter_strings(e):
        label = siyuan_reference(text)
        if label:
            errs.append(f"{crumb} references SiYuan ({label}): a projection is never a source (ADR-0001)")
    if strict:
        for crumb, cit in iter_citations(e):
            if not any(f.match(cit.strip()) for f in CITATION_FORMS.values()):
                errs.append(f"{crumb} is free text; --strict requires one of: {', '.join(CITATION_FORMS)}")
    return errs


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



# --- namespace schemas (ADR-0007) ---------------------------------------------

_SCHEMAS: dict[str, dict | None] = {}


def namespace_schema(namespace: str):
    """schema/<namespace>.schema.json parsed, or None when the namespace has no schema."""
    if namespace not in _SCHEMAS:
        path = ROOT / "schema" / f"{namespace}.schema.json"
        _SCHEMAS[namespace] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return _SCHEMAS[namespace]


def check_attributes(e) -> list[str]:
    """Validate `attributes` against the namespace schema, when there is one."""
    schema = namespace_schema(e["namespace"])
    if schema is None:
        return []
    try:
        import jsonschema
    except ImportError:
        return [f"schema/{e['namespace']}.schema.json exists but the jsonschema package is not installed "
                "(pip install jsonschema)"]
    validator = jsonschema.Draft202012Validator(schema)
    errs = []
    for err in sorted(validator.iter_errors(e.get("attributes", {})), key=lambda x: x.json_path):
        where = "attributes" + err.json_path[1:]
        errs.append(f"{where}: {err.message}")
    return errs

def check(path: Path, strict: bool = False) -> list[str]:
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
    if e["namespace"] in NAMESPACES:
        errs.extend(check_attributes(e))
    errs.extend(check_citations(e, strict))
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

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", nargs="*", metavar="NAMESPACE", default=None,
                    help="require a recognised citation form; bare --strict applies to every "
                         "namespace, or name namespaces (e.g. --strict material) to limit it")
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="entries directory (default: data/)")
    args = ap.parse_args(argv)
    strict_ns = None if args.strict is None else (set(args.strict) or set(NAMESPACES))
    unknown = (strict_ns or set()) - NAMESPACES
    if unknown:
        ap.error(f"unknown namespace(s) for --strict: {sorted(unknown)}")
    data = args.data
    files = sorted(data.rglob("*.json"))
    if not files:
        print("no entries found under data/", file=sys.stderr)
        return 1
    failed = 0
    for f in files:
        errs = check(f, strict=strict_ns is not None and f.parent.name in strict_ns)
        if errs:
            failed += 1
            for e in errs:
                print(f"FAIL {f.relative_to(ROOT) if f.is_relative_to(ROOT) else f}: {e}")
    print(f"{len(files) - failed}/{len(files)} entries valid")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
