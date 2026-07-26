# Roadmap

## Phase 0 - done

- [x] Compiler pipeline skeleton (`observe -> segment -> extract_*`)
- [x] Rule-based statement extractor
- [x] Naive entity extractor (fixed patterns - see note in `pipeline.py`)
- [x] Golden tests (`tests/golden/pr_001`, `tests/golden/pr_002`)

## Phase 1 - finish the prototype (done except LLM/general-NER items)

- [x] Wire `EntityPass`/`SemanticPass` equivalents into `MemoryCompiler.compile()`
      (nothing runs outside of `compile()` now)
- [x] Statement -> Claim -> Fact as a real filter, not two parallel mappers:
      `extract_claims()` scores every Statement (hedge-word heuristic -
      placeholder, see `pipeline._score_confidence`); `extract_facts()`
      promotes a Claim only if `confidence >= FACT_CONFIDENCE_THRESHOLD`
      *and* its predicate maps to a known ontology `Predicate`
- [x] Full provenance chain: `Fact.source_claim` -> `Claim.supporting_statements`
      -> `Statement.id`
- [x] Convert manual test script into real `pytest` tests
- [x] Negative golden test proving a hedged claim is *not* promoted
      (`tests/golden/pr_003_hedged`)
- [x] `pyproject.toml` / `requirements.txt` filled out
- [x] Empty placeholder files removed (`memory/`, `parser/`, `logger.py`,
      `analysis/confidence.py`, `notebooks/*.md`)
- [x] README updated for a clone-and-run-in-under-a-minute quickstart
- [x] Additional artifact shapes beyond PR-style (commit, ADR support with section header parsing)
- [x] `LLMStatementExtractor` - implemented behind `LLMProvider` abstraction (`OpenAIProvider`, `GeminiProvider`, `GenericHTTPProvider`, `MockLLMProvider`)
- [x] General entity recognizer (`GeneralEntityRecognizer` replacing fixed regex list)

## Phase 2 - entity resolution, Relation, and Next-Gen Architecture Infrastructure

- [x] Link Fact subject/object text to the separately-extracted Entity list
      (`DeterministicEntityResolver` with canonical name and alias matching)
- [x] `Relation` IR type (`Entity --predicate--> Entity`), built from
      resolved Facts + Entities via `RuleBasedRelationExtractor`
- [x] Deterministic Hashing & Identity Infrastructure (`deterministic_id`)
- [x] Hierarchical Document Structure preservation (`section_header` and `parent_id` on Observations/Segments)
- [x] Formal `OntologyRegistry` and versioning (`OntologyVersion.V1_0`)
- [x] Typed `CompiledArtifact` compiler output contract with backward-compatible dict access
- [x] MemoryPatch Linker implementation (`ThreePassMemoryPatchLinker`: `BindingPass`, `PersistencePass`, `AnalysisPipeline`)
- [x] Evidence Model (`EvidenceRecord`: One PersistedFact -> Many EvidenceRecords)
- [x] `ArtifactRef` symbol resolution preserving ontology separation between documents and domain entities
- [x] Composable `AnalysisRule` pipeline (`ExplicitDeprecationRule`, `SingleOccupancyDecisionRule`, `DirectNegationConflictRule`)
- [x] In-Memory Persistent Store reference implementation (`InMemoryProjectMemory`)
- [x] `RFC_003_PERSISTENT_IDENTITY_EVIDENCE_AND_MEMORY.md` with explicit Non-Goals section
- [ ] Persistent Disk Storage Engine (SQLite / Parquet format persistence)



## Phase 3 - not started

- [ ] Explanation Engine
- [ ] Compliance Engine

## Explicitly out of scope for now

No vector databases, no graph databases (Neo4j), no embeddings, no agent
loops, no MCP, no orchestration frameworks. None of that solves "can the
compiler deterministically understand one artifact" - which is still the
open problem Phase 1/2 are about.
