# Changelog

## [Unreleased]
### Added
- Repo scaffolded: schema v0, boards namespace with one ingested entry (esp32-s3, from Oh-Ben-Claw registry schema_version 1), stdlib validator, docs and ADRs.
- ADR-0003: hand-rolled binding emitters with golden-fixture parity.
- `scripts/ingest_obc.py`: idempotent ingest of Oh-Ben-Claw's registry. 69 upstream USB-identity rows become **66 board models** carrying `usb_ids` lists (ADR-0004 — neither name nor VID/PID is a key upstream), plus 34 accessories into `electronic` (ADR-0005). 100 entries, all cited, all valid.
- `scripts/emit_ts.py` + `bindings/typescript/parts.ts`: first generated binding, with a `--check` staleness gate so data changes without regenerated bindings fail rather than drift. Compiles under `tsc --strict`.
- Generic passive families: electronic/r-0603 and electronic/c-0603. Package dimensions cited to IPC-SM-782A (via the KiCad footprint that names the page); resistance, dielectric, tolerance and voltage are explicitly properties of the BOM line and of a chosen MPN, not of the family, and are marked TODO(source). Closes the empty-opc_id gap in OpenCircuitCore's BOM. 102 entries.
