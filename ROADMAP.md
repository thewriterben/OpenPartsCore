# Roadmap

## Now
- [x] Schema v0 stabilised against 100 real entries (66 boards + 34 accessories) (2026-08-15)
- [x] `scripts/ingest_obc.py`: idempotent, groups USB identity rows into board models (ADR-0004) (2026-08-15)
- [x] Validation + binding staleness check in CI — plus `tsc --strict` and `cargo test`, the two verifications ARCHITECTURE.md names and neither of which ran anywhere (2026-08-22)

## Next
- [x] Codegen ADR (ADR-0003) and first generated binding: `bindings/typescript/parts.ts`, `--check` staleness gate, compiles under `tsc --strict` (2026-08-15)
- [ ] Report upstream: duplicate board names make name-based selection ambiguous (`esp32-s3`, `arduino-uno`)
- [x] Rust binding (`openpartscore`, zero deps, 7 tests) so Oh-Ben-Claw *can* consume this registry rather than own it (2026-08-15)
- [ ] Oh-Ben-Claw actually switching to it — the other half, and upstream's call
- [ ] `electronic` namespace: first cited entries with KiCad footprint/symbol + atopile package links (for OpenCircuitCore)
- [ ] `material` namespace: first filament entries (for the OpenDesignCore thin thread)

## Not ever
- User inventory data
- Uncited values
- Hand-edited bindings
