# Decisions

Append-only. Newest at the bottom.

---

## ADR-0001 — Schema-first registry with generated bindings

**Date:** 2026-08-15
**Status:** accepted (platform decisions PD-2/PD-3, recorded in OpenDesignCore `wiki/concepts/platform-decisions.md`)

**Context.** Oh-Ben-Claw's `registry.json` is ground truth for ~69 boards, but consumers hand-maintain copies in TS (OBC-deployment-generator) and Python (Accelerapp); drift is documented upstream. The platform needs far more part kinds (electronic, mechanical, material) plus links into EDA tooling, and four consumer languages (Rust, TS, Python, C#).

**Options.** (1) Extend OBC's registry — bloats an agent-deployment registry and keeps the drift mechanism. (2) Federated per-domain registries — cross-domain BOMs stitch multiple sources forever. (3) One canonical schema + data repo with codegen'd bindings.

**Decision.** Option 3, this repo. OBC's registry is ingested as the `boards` namespace with provenance per entry; OBC remains upstream for its own fields and eventually consumes the generated Rust binding. User inventory is explicitly out of scope — separate store, references part ids.

**Consequences.** A codegen toolchain becomes load-bearing (choice of tool is an open question — quicktype vs. hand-rolled emitters — needs its own ADR before bindings ship). Schema changes become platform-wide events and get versioned (`schema_version`). Until bindings exist, consumers may read the JSON directly but must not vendor the model.

---

## ADR-0002 — Apache-2.0

**Date:** 2026-08-15
**Status:** accepted (PD-4; mirrors OpenDesignCore ADR-0005)

Express patent grant in a domain encoding manufacturing data; uniform with OpenDesignCore and the PicoGK stack. Adopted at creation, before any external contribution.
