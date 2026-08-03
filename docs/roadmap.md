# Roadmap

## Phase 0 — done

- [x] Compiler pipeline skeleton (`observe -> segment -> extract_*`)
- [x] Rule-based statement extractor
- [x] Entity extractor
- [x] Golden IR tests

## Phase 1 — done

- [x] `Statement -> Claim -> Fact` as a real filter, not two parallel mappers
- [x] Full provenance chain: `Fact.source_claim -> Claim.supporting_statements -> Statement.id`
- [x] Negative golden proving a hedged claim is not promoted
- [x] Artifact shapes beyond PR-style (commit, ADR, section header parsing)
- [x] `LLMStatementExtractor` behind an `LLMProvider` abstraction
- [x] General entity recognizer replacing the fixed regex list

## Phase 2 — done

- [x] Entity resolution linking fact operands to extracted entities
- [x] `Relation` IR type, and the linker actually consumes it
- [x] Deterministic hashing and identity (`deterministic_id`)
- [x] Hierarchical document structure preserved (`section_header`, `parent_id`)
- [x] Versioned `OntologyRegistry`
- [x] Typed `CompiledArtifact` output contract
- [x] `ThreePassMemoryPatchLinker` (binding, persistence, analysis)
- [x] Evidence model: one `PersistedFact` → many `EvidenceRecord`
- [x] `ArtifactRef` ontology separation
- [x] Composable `AnalysisRule` pipeline
- [x] In-memory reference store
- [x] **SQLite persistence engine** with a shared conformance suite
- [x] RFC 003 with explicit non-goals

## Phase 2.5 — the read path (done)

Added after building a resolver falsified four write-side assumptions. See
`docs/findings/read-path.md` and RFC 004.

- [x] `BeliefResolver` — memory → current belief, history, evidence, diagnostics
- [x] `BeliefReader` contract, separate from the linker's `MemoryReader`
- [x] Entity-anchored extraction (the fix for artifact-anchored facts)
- [x] Temporal ordering: belief invariant under ingestion permutation
- [x] Supersession provenance (`source_artifact_id`, `recorded_at`, `basis`)
- [x] Weighable evidence (claim confidence × artifact-type authority)
- [x] Entity identity hashed on name only, not `(type, name)`
- [x] Deterministic compiler-local ordinals, making reproducibility testable
- [x] `tests/test_import_boundaries.py` — architectural invariants as assertions
- [x] Scenario goldens with `expected_belief.json`
- [x] `pme` CLI: `compile` / `ingest` / `ask` / `stats`

## Phase 3 — next

- [ ] **Entity aliasing and merge semantics.** `API Gateway` / `the gateway` /
      `APIGW` are three permanent identities in an append-only store. Candidate:
      a `SAME_AS` edge resolved at read time, so a merge is an assertion with
      evidence rather than a mutation. The hardest remaining identity problem,
      and the one that compounds with corpus age.
- [ ] **Richer extraction.** The pattern table is a floor. Either more patterns
      or an LLM extractor behind the same interface — the shape of the output
      matters, not the matcher.
- [ ] **Ontology evolution.** V1 → V2 migration semantics. RFC 002 specifies the
      registry; what happens to facts compiled under an older ontology is open.
- [ ] **Query beyond single-entity lookup.** "What changed in authentication
      between 2023 and 2025", "what depends on Redis".

## Phase 4 — applications, once Phase 3 settles

- [ ] Explanation engine (natural-language rendering over `ResolvedBelief`)
- [ ] Compliance engine
- [ ] Onboarding assistant

These sit *on* the resolver. If each builds its own resolution, they will
disagree with each other about what the project believes.

## Explicitly out of scope

No vector databases, no graph databases, no embeddings, no agent loops, no MCP,
no orchestration frameworks. None of them answer the open question, which is
whether a project can build and justify knowledge about itself deterministically.
