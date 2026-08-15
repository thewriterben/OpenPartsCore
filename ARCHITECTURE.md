# Architecture

```
schema/part.schema.json     the one definition of a part entry (JSON Schema 2020-12)
data/<namespace>/<id>.json  one part per file, schema-valid, cited
scripts/validate.py         stdlib validator: structure, citations, unit-suffix rules
bindings/                   generated code (Rust/TS/Python/C#) — never hand-edited (none yet)
```

## Grounding

This repo is reviewable reference data in the sense of OpenDesignCore ADR-0006: values arrive by pull request with citations, changes are visible in diffs. Downstream model runs may read values from here (via bindings) because every value is cited; nothing here is LLM-synthesised knowledge.

## Boards namespace ingest

`data/boards/` entries are derived from Oh-Ben-Claw `registry/registry.json` (schema_version 1). The ingest preserves OBC's fields under `attributes` verbatim and records the upstream file + schema_version in `source`. Re-ingest is idempotent by part id. OBC is not forked: corrections to board facts go upstream first.

## What does not live here

- User inventory (mutable state; separate store referencing part ids)
- Pricing/stock (volatile; fetched live from distributor APIs by consumers, keyed by ids here)
- Kernel-side geometry (3D models are linked by path/hash, not embedded)
