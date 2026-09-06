# OpenPartsCore

The canonical parts registry for the OpenDesignCore platform: one schema, one set of data files, generated bindings for every consumer language.

**Status:** pre-alpha. Schema v0.

## What it is

- A **JSON Schema** (`schema/part.schema.json`) defining what a part entry is.
- **Data files** (`data/<namespace>/*.json`), one part per file, schema-validated, every entry citing its source.
- **Generated bindings** (`bindings/`, none yet) for Rust, TypeScript, Python, and C# — consumers never hand-copy the data model. This is the fix for the registry drift documented in Oh-Ben-Claw's ECOSYSTEM-INTEGRATION.md.

## Namespaces

| Namespace | Contents | Primary source |
|---|---|---|
| `boards` | Dev boards / SBCs / MCU modules | Ingested from Oh-Ben-Claw `registry/registry.json` (schema_version 1) — not forked; OBC remains upstream for agent-deployment fields |
| `electronic` | ICs, passives, connectors, modules | Datasheets + distributor data; links KiCad footprints/symbols and atopile packages |
| `mechanical` | Motors, fasteners, bearings, stock | Vendor drawings/datasheets |
| `material` | Filament, resin, sheet stock | Vendor TDS |

## Rules

- **Every entry carries a citation.** An uncited value fails validation. No plausible-looking numbers.
- **Length fields are millimetres** and end in `_mm` (matches OpenDesignCore ADR-0004). Other units are named in the field (`mass_g`, `voltage_v`).
- **An envelope carries its own source.** `envelope_mm` is optional; when present it has all three axes and a citation of its own, because the entry's citation (for ingested boards, a registry with no dimensions) does not cover it. Absent means unknown, never zero (ADR-0006).
- **User inventory does not live here.** Inventory is mutable user state referencing canonical part ids; this repo is reviewable reference data only (platform decision PD-2).

## Validate

```
python scripts/validate.py
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
