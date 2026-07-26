# Session Changelog - Project Memory Engine

This document tracks all design decisions, architectural improvements, and code changes implemented during this session.

---

## 1. Markdown Header Parsing & ADR / Commit Artifact Support

- **Issue**: Chunks starting with `#` or `##` (e.g. `## Status\nAccepted`) were unconditionally classified as `"header"` observations in `observe()` and completely dropped in `segment()`, causing total data loss for standard Markdown ADRs and structured docs.
- **Fix**:
  - **[pipeline.py](file:///Users/arnav/Desktop/project-memory-engine/memory_engine/pipeline.py)**: Updated `observe()` to separate header lines from section body text. Parsed section title headers (`Status`, `Context`, `Decision`, `Consequences`, `Reason`, `Trade-off`) to assign observation types while preserving body text.
  - **[ir.py](file:///Users/arnav/Desktop/project-memory-engine/memory_engine/ir.py)**: Added `DECISION`, `CONTEXT`, `STATUS`, and `CONSEQUENCE` enum values to `SegmentKind`.
  - **[extractors.py](file:///Users/arnav/Desktop/project-memory-engine/memory_engine/extractors.py)**: Mapped new segment kinds to ontology predicates (`selected`, `has_reason`, `describes`, `has_tradeoff`).
  - **Sample & Test Additions**: Added `samples/sample_adr.md`, `samples/sample_commit.md`, and auto-discovered golden test suites `tests/golden/adr_001` and `tests/golden/commit_001`.

---

## 2. Phase 1 Extractor Upgrades

- **`LLMStatementExtractor` & `LLMProvider` Abstraction**:
  - Defined abstract `LLMProvider` interface in `extractors.py`.
  - Implemented `OpenAIProvider`, `GeminiProvider`, `GenericHTTPProvider`, and `MockLLMProvider`.
  - Configured `LLMStatementExtractor` to accept `provider: LLMProvider` (`__init__(provider)`), keeping statement extraction provider-agnostic.
  - Added API key validation checking `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `LLM_API_KEY` from `os.environ`, raising descriptive `ValueError` exceptions if credentials are missing.
- **Decoupled `GeneralEntityRecognizer`**:
  - Created `EntityRecognizer(ABC)` interface and `GeneralEntityRecognizer` implementation in `extractors.py`.
  - Replaced the fixed demo pattern list with general software tech stack entity recognition (`PostgreSQL`, `Redis`, `Kubernetes`, `React`, `OAuth`, `Kafka`, `API Gateway`, `JWT validation`, `authentication`, PascalCase code identifiers).
  - Decoupled recognition from ontology classification by setting `entity_type = EntityType.UNKNOWN` unless explicit structural hints match.
  - Integrated `EntityRecognizer` into `extract_entities()` and `MemoryCompiler.__init__()` in `pipeline.py`.

---

## 3. Phase 2 Entity Resolution & `Relation` IR Construction

- **Public `Relation` IR Type**:
  - Added `Relation` dataclass (`id`, `subject_entity_id`, `predicate`, `object_entity_id`, `source_fact_id`, `confidence`) to [ir.py](file:///Users/arnav/Desktop/project-memory-engine/memory_engine/ir.py).
- **Internal Helper Structure**:
  - Created `ResolvedFact` helper strictly inside `extractors.py` as an internal compiler transfer object between passes (kept out of public `ir.py`).
- **Entity Resolution & Relation Extraction Passes**:
  - Implemented `DeterministicEntityResolver`: performs exact canonical name and explicit alias matching (case-insensitive).
  - Implemented `RuleBasedRelationExtractor`: constructs `Relation` IR objects when both subject and object entities are resolved.
  - **Inherited Confidence Propagation**: `Relation.confidence` inherits confidence from originating `Claim` provenance via `Fact.source_claim` rather than defaulting to `1.0`.
  - **Fail-Safe Ambiguity Handling**: If a lookup key maps to $\ge 2$ distinct `Entity` objects, the resolver marks it ambiguous and returns `None` (unresolved) rather than guessing or picking the last entity encountered.
- **Pipeline Integration**:
  - Added `resolve_entities()` and `extract_relations()` stages to `MemoryCompiler.compile()` in `pipeline.py`.
  - Included `"relations"` in `MemoryCompiler.compile()` result dictionary.

---

## 4. Test Suite & Specification Integrity

- Expanded test coverage in `tests/test_entities_and_facts.py` from 8 to **16 passing tests**:
  - `test_general_entity_recognizer_software_concepts()`
  - `test_llm_statement_extractor_with_mock_provider()`
  - `test_llm_provider_raises_missing_api_key()`
  - `test_entity_resolution_and_relation_extraction()`
  - `test_unresolved_entities_do_not_produce_relations()`
  - `test_ambiguous_entities_remain_unresolved()`
- Guaranteed 100% backward compatibility with all 10 existing golden test `expected.json` files.

---

## 5. Documentation Updates

- Updated [docs/roadmap.md](file:///Users/arnav/Desktop/project-memory-engine/docs/roadmap.md) marking completed Phase 1 and Phase 2 items.
- Created `docs/changelog.md` for permanent documentation of session improvements.

---

## 6. Next-Generation Architecture Refactoring

- **Deterministic Identity & Scoped Identity Engine**:
  - Implemented `deterministic_id(scope, *components)` helper generating stable SHA-256 content-addressed IDs for `Artifact`, `Entity`, and persistent graph facts.
  - Assigned deterministic local ordinal IDs (`obs:0`, `seg:1`, `stmt:2`) to transient compiler nodes.
- **Hierarchical Document Structure Invariant**:
  - Added `section_header` and `parent_id` fields to `Observation` and `Segment` dataclasses.
  - Updated `observe()` and `segment()` in `pipeline.py` to record and attach section titles and parent observation IDs so structural document hierarchy survives compilation.
- **Standalone Versioned Ontology Layer (`OntologyRegistry`)**:
  - Introduced `OntologyVersion.V1_0` and `OntologyRegistry` class in `ontology.py`.
  - Decoupled hardcoded extraction dictionaries so `RuleBasedStatementExtractor` and `RuleBasedFactExtractor` query `OntologyRegistry`.
- **Compiler Output Contract (`CompiledArtifact`)**:
  - Replaced raw dictionary outputs from `MemoryCompiler.compile()` with a typed, immutable `CompiledArtifact` dataclass.
  - Implemented `dict` indexing (`__getitem__`), `.to_dict()`, `.to_json()`, and inspection properties (`fact_count`, `relation_count`) to preserve 100% backward compatibility with all golden tests and existing test suites.
- **MemoryPatch Linker Contracts (`memory_engine/patch.py`)**:
  - Defined Phase 2 MemoryPatch contract specifications: `MemoryReader` (ABC snapshot query interface), `MemoryDelta` (immutable append-only delta log), and `MemoryPatchLinker` (ABC linker interface).
- **Architecture RFC Specifications**:
  - Created `docs/rfcs/RFC_001_COMPILER_LINKER_ARCHITECTURE.md` (Compiler/Linker boundary, `CompiledArtifact` contract, identity system, linker invariants).
  - Created `docs/rfcs/RFC_002_ONTOLOGY_REGISTRY_AND_EVOLUTION.md` (Ontology layer ownership, versioning schema, linker migration mapping).
---

## 7. Three-Pass MemoryPatch Linker Engine & Evidence Model

- **Three-Pass Linker Pipeline (`ThreePassMemoryPatchLinker`)**:
  - **Pass 1 (`BindingPass`)**: Binds local entities to persistent global IDs; resolves `$ARTIFACT_SELF` / `CURRENT_CHANGE` to `ArtifactRef(artifact_id)`, preserving strict ontology separation between evidence documents and domain concepts. Unresolved entities safely remain unresolved.
  - **Pass 2 (`PersistencePass`)**: Promotes compiler facts to content-addressed `PersistedFact` nodes ($O(1)$ deduplication) and accumulates `EvidenceRecord` entries when multiple artifacts support the same fact.
  - **Pass 3 (`AnalysisPipeline`)**: Runs an ordered sequence of deterministic `AnalysisRule` plugins (`ExplicitDeprecationRule`, `SingleOccupancyDecisionRule`, `DirectNegationConflictRule`).
- **Evidence Model (`EvidenceRecord`)**:
  - Implemented `EvidenceRecord` dataclass (`id`, `persisted_fact_id`, `source_artifact_id`, `source_fact_id`, `confidence`, `supporting_statements`).
  - Supports: **One PersistedFact $\rightarrow$ Many EvidenceRecords**. Multiple artifacts asserting the same relationship accumulate evidence without graph node duplication.
- **Reference In-Memory Persistent Store (`InMemoryProjectMemory`)**:
  - Implemented monotonic append-only temporal property graph providing snapshot queries (`MemoryReader`) and delta application (`apply_delta`).
- **`RFC_003_PERSISTENT_IDENTITY_EVIDENCE_AND_MEMORY.md`**:
  - Created formal RFC specifying Persistent Identity, Evidence Model, `ArtifactRef` symbol resolution, `AnalysisRule` Pipeline Architecture, and an explicit **Non-Goals** section.
- **Test Suite Expansion**:
  - Added `tests/test_memory_linker.py` covering single artifact linking, 3x repeated linker execution idempotency, cross-artifact evidence accumulation, `ArtifactRef` symbol resolution, conservative single-occupancy decision rules, and custom `AnalysisRule` plugins.
  - Re-ran pytest suite: **33 passed in 0.02s** (100% pass rate).


