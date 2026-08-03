# Changelog

## 0.3.0 — read path, time, and restructure

Built the first resolver over persistent memory. It falsified four write-side
assumptions on day one; most of this release is the consequence. Full account in
`docs/findings/read-path.md`; specification in RFC 004.

### Added

- `memory_engine.resolve` — `BeliefResolver`, `ResolvedBelief`, `BeliefNode`,
  `render`. The read path, positioned as a sibling of compiler and linker rather
  than as a Phase 3 application.
- `memory_engine.memory` — persistent schema and store contracts extracted into
  their own package. The linker writes these types and the resolver reads them,
  so neither depends on the other.
- `BeliefReader` contract, separate from the linker's `MemoryReader`.
- `memory_engine.store.sqlite` — durable store. No `UPDATE` or `DELETE` anywhere;
  asserted against the module's SQL literals.
- `tests/contracts/test_store_conformance.py` — one suite, every store.
- `memory_engine.linker.ordering` — temporal comparison for supersession.
- `RelationalStatementExtractor` and `PhraseEntityRecognizer`, sharing one
  pattern table so a fact operand cannot exist without its entity.
- `memory_engine.ingest` — the only module wiring compiler, linker, and store.
- `memory_engine.cli` — `pme compile` / `ingest` / `ask` / `stats`.
- `tests/test_import_boundaries.py` — AST-level enforcement of layer boundaries.
- Scenario fixtures with `manifest.json` and `expected_belief.json`; tested for
  permutation-invariance, cross-store agreement, and survival across reopen.
- RFC 004; `docs/findings/read-path.md`; CI across Python 3.11–3.13.

### Changed — behaviour

- **Facts are entity-anchored.** Previously every persisted fact had the artifact
  as its subject and a whole paragraph as its object, so no question about a
  concept was answerable, deduplication could never fire, and supersession could
  never fire. Artifact-level assertions still exist and still use `ArtifactRef`.
- **Supersession is ordered by time, not arrival.** An artifact that pre-dates
  what is stored is now itself superseded. Equal timestamps with incompatible
  content produce a `ConflictEdge` rather than a coin flip. Missing timestamps
  fall back to ingestion order and record `basis="ingestion_order"`, which the
  resolver reports. Belief is now invariant under ingestion permutation.
- **Evidence carries real values.** Claim confidence, artifact type, and type
  authority replace a hardcoded `1.0`. `BeliefNode.support` is derived at read
  time and never stored; it measures commitment, not probability of truth.
- **Entity IDs hash the canonical name only**, not `(type, name)`. Two artifacts
  disagreeing about whether OAuth2 is a framework or a feature no longer fork the
  entity.
- **Compiler-local IDs are deterministic ordinals** (`obs:0`, `stmt:3`) inside a
  compilation scope, per RFC 003 §2. They were UUIDs, which made the
  reproducibility guarantee untestable.
- **The linker consumes `Relation`.** It was computed and discarded.
- **`ExplicitDeprecationRule` retires object-position facts**, so "replace JWT
  with OAuth2" retires `auth --selected--> JWT`. Needed
  `get_active_facts_with_object` on the reader contract.
- **`InMemoryProjectMemory` is idempotent**, matching SQLite. The conformance
  suite caught the divergence.
- Golden files regenerated for the new statement shape.

### Changed — structure

Flat `memory_engine/` split into `compiler/`, `memory/`, `linker/`, `store/`,
`resolve/`. `patch.py` — which held the schema, the passes, the rules, and the
store — split along those four seams. `samples/` → `fixtures/artifacts/`;
`tests/golden/` → `tests/compiler/golden/`.

### Documented

RFC 001's determinism claim is amended. Compilation is reproducible given
`(content, compiler version, ontology version, extractor config)` — a recorded
tuple, not an absolute. `CompiledArtifact` stores the versions.

### Tests

33 → 140.

---

## 0.2.0 — linker and evidence model

- `ThreePassMemoryPatchLinker`: binding, persistence, analysis
- Evidence model: one `PersistedFact` → many `EvidenceRecord`
- `ArtifactRef` symbol resolution
- Composable `AnalysisRule` pipeline
- `InMemoryProjectMemory`
- RFC 003

## 0.1.0 — compiler

- `Artifact → Observation → Segment → Statement → Claim → Fact`
- Ontology registry and versioning
- Entity resolution and `Relation`
- Typed `CompiledArtifact`
- Golden tests
