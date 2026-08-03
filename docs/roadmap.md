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

## Phase 3 — done

- [x] **Entity aliasing and merge semantics.** `SAME_AS` as an ordinary fact
      with evidence, resolved into equivalence classes at read time. Cycle-safe,
      bounded, deterministic canonical member. A retracted merge is a
      supersession, not a deletion.
- [x] **Query beyond single-entity lookup.** `timeline`, `dependents`, `health`.
- [x] **Measured extraction.** `memory_engine/eval/` with labelled corpora.
      Precision and recall are numbers now, not impressions.
- [x] **Richer extraction.** Nine further relational patterns, sentence-level
      matching, markdown-aware chunking, negation as constraint.

## Phase 3.5 — done

- [x] **Compound-sentence splitting.** Clause-level matching, conservative about
      what counts as a coordinator.
- [x] **Verb inflection in patterns.** use/uses/used/using, depend/depends/upon.
- [x] **Determiner-based concept detection.** A grammatical signal instead of a
      word list: "the storefront" marks storefront as a named thing. Closed
      vocabularies were failing on every project that names things differently.
- [x] **A third, adversarial eval corpus** (`hard-realistic`) with conversational
      decisions, buried rejections, and an unimplemented action item that must
      NOT become a fact. Scores badly on purpose.
- [x] **Ontology evolution.** A rename is a declared equivalence applied at read
      time, never a rewrite. `OntologyMigrator.plan()` reports impact; there is
      deliberately no `apply()`, because facts are never rewritten.

## Phase 5 — deployment path (done, except where noted)

- [x] **Real ingestion.** `GitSource`, `FilesystemSource`, `GitHubSource` (with
      review comments, where the reasoning actually lives). Incremental by
      watermark; a second run does no work.
- [x] **Correction loop.** A human correction is an artifact with an author, a
      date, and the highest authority in the table. Retires a fact through
      ordinary supersession; deletes nothing.
- [x] **Scale.** Indexed `UNION` lookups and a recursive-CTE identity closure.
      Sub-millisecond at 40k facts, asserted by a test.
- [x] **LLM extraction architecture.** `CachedLLMStatementExtractor` pins and
      caches on `(text, model, prompt version, temperature, provider)`, keeping
      RFC 004 §3 true. A model upgrade is a new compilation, not a rewrite.
- [x] **Pilot interface and measurement.** MCP server (`pme serve`) and
      `pme pilot`, which counts wrong answers separately from declined ones.

## Phase 6 — what cannot be finished from inside this repository

- [ ] **The answerability check.** 30 real ADRs, 20 real questions, hand-checked.
      Two days, needs your repository, and it is the only item that can
      invalidate everything above.
- [ ] **Independently labelled extraction corpus.** The labels and the extractor
      share an author, so current numbers show absence of regression rather than
      capability. Structural, not a matter of remaining effort.
- [ ] **Extraction beyond surface patterns.** `hard-realistic` sits at 25%
      reachable recall. Conversational decisions and cross-sentence coreference
      need the LLM extractor the architecture now supports — the wiring is done,
      the validation is not.

## Phase 4 — applications

- [x] **Explanation engine** (`resolve/explain.py`). Prose over `ResolvedBelief`;
      every sentence traces to a stored value, no model call, caveats surfaced
      rather than smoothed.
- [ ] Compliance engine — check a codebase against recorded constraints
      (`PROHIBITS` facts are already extracted and stored)
- [ ] Onboarding assistant

These sit *on* the resolver. If each builds its own resolution, they will
disagree with each other about what the project believes.

## Explicitly out of scope

No vector databases, no graph databases, no embeddings, no agent loops, no MCP,
no orchestration frameworks. None of them answer the open question, which is
whether a project can build and justify knowledge about itself deterministically.
