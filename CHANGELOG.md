# Changelog

## [Unreleased]
### Added
- Repo scaffolded: schema v0, boards namespace with one ingested entry (esp32-s3, from Oh-Ben-Claw registry schema_version 1), stdlib validator, docs and ADRs.
- ADR-0003: hand-rolled binding emitters with golden-fixture parity.
- `scripts/ingest_obc.py`: idempotent ingest of Oh-Ben-Claw's registry. 69 upstream USB-identity rows become **66 board models** carrying `usb_ids` lists (ADR-0004 — neither name nor VID/PID is a key upstream), plus 34 accessories into `electronic` (ADR-0005). 100 entries, all cited, all valid.
- `scripts/emit_ts.py` + `bindings/typescript/parts.ts`: first generated binding, with a `--check` staleness gate so data changes without regenerated bindings fail rather than drift. Compiles under `tsc --strict`.
- Generic passive families: electronic/r-0603 and electronic/c-0603. Package dimensions cited to IPC-SM-782A (via the KiCad footprint that names the page); resistance, dielectric, tolerance and voltage are explicitly properties of the BOM line and of a chosen MPN, not of the family, and are marked TODO(source). Closes the empty-opc_id gap in OpenCircuitCore's BOM. 102 entries.
- `scripts/emit_rust.py` + `bindings/rust/`: the Rust binding Oh-Ben-Claw needs to consume this registry instead of carrying its own copy — the drift its own docs describe. Crate `openpartscore`, **zero dependencies**, whole registry as const data with no runtime parsing. `capabilities` and `usb_ids` are hoisted and typed; everything else stays as `attributes_json`.
- `candidates_for_usb(vid, pid)` returns an **iterator, not an Option** — the API makes ADR-0004's many-to-many mapping impossible to ignore. 7 `cargo test` cases pin it, including that `0x303a:0x1001` yields more than five candidate boards and that one board holds three identities.
- `--check` staleness gate matches the TypeScript emitter's; both bindings and the validator are green at 102 entries.
