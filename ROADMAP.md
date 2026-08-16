# Roadmap

## Now
- [x] Schema v0 stabilised against 100 real entries (66 boards + 34 accessories) (2026-08-15)
- [x] `scripts/ingest_obc.py`: idempotent, groups USB identity rows into board models (ADR-0004) (2026-08-15)
- [ ] Validation + binding staleness check in CI

## Next
- [x] Codegen ADR (ADR-0003) and first generated binding: `bindings/typescript/parts.ts`, `--check` staleness gate, compiles under `tsc --strict` (2026-08-15)
- [ ] Report upstream: duplicate board names make name-based selection ambiguous (`esp32-s3`, `arduino-uno`)
- [ ] Rust binding, so Oh-Ben-Claw can consume this registry rather than own it
- [ ] `electronic` namespace: first cited entries with KiCad footprint/symbol + atopile package links (for OpenCircuitCore)
- [ ] `material` namespace: first filament entries (for the OpenDesignCore thin thread)

## Not ever
- User inventory data
- Uncited values
- Hand-edited bindings
