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

---

## ADR-0003 — Hand-rolled binding emitters, not quicktype

**Date:** 2026-08-15
**Status:** accepted

**Context.** ADR-0001 promises generated bindings for Rust, TS, Python, and C#. Two routes: quicktype (mature multi-language generator consuming JSON Schema) or small hand-rolled emitters (Python stdlib scripts reading schema + data, emitting each language).

**Options.**
1. quicktype — broad language coverage for free, but a Node toolchain dependency, output style we don't control, and its output still needs per-language wrapping (id types, namespace enums, data embedding vs. loading).
2. Hand-rolled emitters — we own ~4 small templates; schema v0 is deliberately tiny (one object type, one enum, one nested source/links pair), which is exactly the case where a generator earns least.

**Decision.** Option 2. `scripts/emit_<lang>.py`, stdlib only (matching the validator and the BINGO v3 precedent). Correctness by golden fixtures, borrowing OBC-Prime's parity discipline: every emitter's output for the committed data set is itself committed, CI regenerates and diffs — byte-identical or red.

**Consequences.** Adding a language is writing an emitter, not configuring a tool. If schema complexity ever outgrows this (unions, deep polymorphism), revisit quicktype in a superseding ADR — the schema staying emitter-simple is a feature, not an accident. First target is TS (OBC-deployment-generator), second Rust (Oh-Ben-Claw).

---

## ADR-0004 — A board is not a USB identity

**Date:** 2026-08-15
**Status:** accepted

**Context.** Ingesting Oh-Ben-Claw's `registry.json` (schema_version 1) exposed a shape that neither repo had written down. The file reads as a list of boards, but it is a list of **USB identity rows**: 69 rows covering **66 board models** and **44 distinct VID/PID pairs**. Neither field is a key.

- One board, several identities: `esp32-s3` appears three times (native USB `303a:1001`, CP2102 `10c4:ea60`, CH343 `1a86:7523`); `arduino-uno` twice.
- One identity, several boards: `303a:1001` is shared by **17** board models, `1a86:7523` (CH340) by 5, `10c4:ea60` (CP2102) by 4, and `0955:7020` by both Jetson Nano and Orin Nano.

This is not upstream sloppiness — it is what USB actually does, since a bridge chip's identity says nothing about the board it is soldered to. Oh-Ben-Claw's hardware-scout reports note the consequence in passing ("registry resolves these by selecting on `name`, not VID/PID"), but with duplicate names present that rule is incomplete on its own.

**Options considered.**
1. Mirror upstream row-for-row — inherits a structure where no field identifies an entry, and makes `boards/esp32-s3` ambiguous.
2. Key on VID/PID — collides 5 ways, worst case 17 boards to one id.
3. One entry per **board model**, carrying its identities as a list.

**Decision.** Option 3. A canonical entry is a board model, id `boards/<name-slug>`, with `attributes.usb_ids: [{vid, pid, architecture}]` sorted by `(vid, pid)`, and capabilities/connectors unioned across the merged rows. `scripts/ingest_obc.py` performs the grouping and is idempotent: an unchanged upstream rewrites nothing.

**Consequences.** Identification becomes explicitly a *match* problem, not a lookup: enumerating `303a:1001` narrows to 17 candidates and needs another signal (a probe, or the user saying which board they own). That is the honest model, and it is better to make callers confront it than to have a lookup silently return the first match. Upstream keeps its row-oriented shape; this repo does not fork it, and a correction to a board fact still goes to Oh-Ben-Claw first. **Worth reporting upstream:** the duplicate-name rows mean name-based selection is ambiguous for `esp32-s3` and `arduino-uno` today.

---

## ADR-0005 — Accessories are electronic parts

**Date:** 2026-08-15
**Status:** accepted

**Context.** Upstream splits `boards` and `accessories`. This repo's namespaces are `boards | electronic | mechanical | material` (ADR-0001), with no accessory namespace.

**Decision.** Upstream accessories — sensors, displays, HATs, accelerator modules — ingest into `electronic`, keeping `bus`, `default_i2c_addr`, `capabilities`, `compatible_boards`, and `connector` under `attributes`.

**Consequences.** `electronic` will eventually hold both breakout modules and bare components (ICs, passives) once OpenCircuitCore's reference board needs them. That is intended: they are the same kind of thing to a BOM, differing in packaging. If the distinction later earns its keep, it becomes a field, not a namespace — namespaces are expensive to change because they are baked into every id.

---

## ADR-0006 — An envelope carries its own source

**Date:** 2026-09-06
**Status:** accepted

**Context.** OpenDesignCore's thin thread is "a component from the registry → an enclosure around its dimensions". Its `run_enclosure` reads envelopes from a private `data/parts/` holding one hand-copied module, because *this* registry — the one the thread is named after — carried no dimensions at all. Every `boards/*` entry has exactly one `source`, and it is Oh-Ben-Claw's `registry.json`, which has never held a length. Adding `x, y, z` under that citation would put a number under a source that does not cover it: it would validate, it would look sourced, and it would be the invented-value failure wearing a citation. Two further facts shaped the shape: `ingest_obc.py` rewrites every board file from upstream, so a hand-added field is deleted by the next run; and the generic `boards/esp32-s3` groups three USB bridges under one name, so there is no single drawing it could cite.

**Options.**
1. `attributes.envelope_mm` under the entry's existing source — rejected for the reason above; `attributes` is documented as "preserved verbatim from the cited source", and upstream has no such field.
2. A parallel `physical/` namespace keyed to the same slug — splits one part across two ids and forces every consumer to join.
3. Optional top-level `envelope_mm {x, y, z, tolerance_mm?, source}` with a mandatory citation of its own; the ingest preserves it.

**Decision.** Option 3. `envelope_mm` is optional and, when present, complete (all three axes), positive, and cited *in itself*. Absent means unknown, never zero — the same rule as ClawBot's `limits: null`. `scripts/ingest_obc.py` now carries `envelope_mm` and `links` across a re-ingest (`PRESERVED_KEYS`): they are the fields upstream cannot supply, so the ingest must not remove them. The Rust binding hoists it as `Option<EnvelopeMm>` with the citation inline, so a consumer that reads `x` is one field away from where `x` came from. A derived envelope is acceptable when the derivation is stated in full: the first board entry is the bounding box of the vendor's own STEP model, with the file's hash, the tool and version, the meshing tolerance, the unrounded result and what the box does and does not include, all in the citation.

**Consequences.** Most entries will have no envelope for a long time, and the generic multi-bridge boards never can; that is correct and visible. OpenDesignCore can now read this registry instead of its private store (its ROADMAP's "consume, don't fork" item), and entries without an envelope are simply not offered to `run_enclosure` rather than defaulted. A schema field with its own `source` is a precedent: any future fact that does not come from the entry's source (mass, a mounting-hole pattern) follows this shape rather than borrowing the entry's citation. The re-ingest is idempotent only within a day — `source.retrieved` is stamped with today's date — which predates this ADR and is left as it was.
