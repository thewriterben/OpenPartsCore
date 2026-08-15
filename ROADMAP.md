# Roadmap

## Now
- [ ] Schema v0 stabilised against real entries (1 board ingested; grow to full OBC boards ingest)
- [ ] `scripts/ingest_obc.py`: idempotent Oh-Ben-Claw registry → `data/boards/` converter
- [ ] Validation in CI

## Next
- [ ] Codegen ADR (quicktype vs. hand-rolled) and first generated binding (TS, for OBC-deployment-generator)
- [ ] `electronic` namespace: first cited entries with KiCad footprint/symbol + atopile package links (for OpenCircuitCore)
- [ ] `material` namespace: first filament entries (for the OpenDesignCore thin thread)

## Not ever
- User inventory data
- Uncited values
- Hand-edited bindings
