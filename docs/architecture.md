# Architecture

Project Memory Engine turns a software artifact (PR, commit, ADR, issue, ...)
into structured facts, entities, and claims about the project.

## Pipeline

```
Artifact
   |
   v
observe()             -> Observation   (typed paragraphs)
   |
   v
segment()             -> Segment       (description / reason / tradeoff)
   |
   +--> extract_statements()  -> Statement  (subject, predicate, target)
   |         |
   |         v
   |     extract_claims()     -> Claim      (confidence-scored assertion)
   |         |
   |         v
   |     extract_facts()      -> Fact       (Claim, filtered + normalized)
   |
   +--> extract_entities()    -> Entity  (named things mentioned)
```

Entity is a parallel branch off Segment, not a downstream consumer of Fact -
entity extraction doesn't need a statement to have been built from a
sentence, it just needs the sentence.

`MemoryCompiler.compile()` in `memory_engine/pipeline.py` runs every stage
above in order and returns a typed `CompiledArtifact` instance. There is no stage that runs but
isn't called from `compile()` - if it's in the file, it's in the pipeline.

## Compiler-Linker Decoupling

The engine follows a strict Compiler/Linker architecture:

- **Compiler (`MemoryCompiler`)**: Pure, stateless single-artifact knowledge extractor. Consumes one `Artifact` and emits a typed `CompiledArtifact` object.
- **Linker (`MemoryPatchLinker`)**: Stateful cross-artifact knowledge linker. Consumes `CompiledArtifact` and `MemoryReader`, emitting an append-only `MemoryDelta`.

## Core Architectural Invariants

1. **Deterministic Hashing & Identity**: Artifacts, Entities, and Persisted Facts use stable content-addressed IDs (`deterministic_id`). Transient compiler nodes use local ordinal identifiers (`obs:0`, `seg:1`).
2. **Hierarchical Document Preservation**: `Observation` and `Segment` record section headers (`section_header`) and parent IDs (`parent_id`) so structural document context survives compilation.
3. **Ontology Registry**: Managed by a versioned `OntologyRegistry` (`OntologyVersion.V1_0`). The compiler queries the registry for predicate and entity type normalization.
4. **Typed Compiler Output Contract**: `MemoryCompiler.compile()` returns a `CompiledArtifact` object, providing full dictionary compatibility (`__getitem__`, `to_dict()`, `to_json()`) alongside typed properties.

## Claim vs. Fact

These are deliberately separate compiler IR representations:

- **Claim** - Epistemic IR: anything the artifact asserts, scored with a confidence heuristic.
- **Fact** - Normalized Ontology IR: a `Claim` that `FactPass` has accepted as structured knowledge (confidence >= `FACT_CONFIDENCE_THRESHOLD` and predicate normalized by `OntologyRegistry`).

## Modules

- `memory_engine/ir.py` - IR data types (`Artifact`, `Observation`, `Segment`, `Statement`, `Entity`, `Claim`, `Fact`, `Relation`, `CompiledArtifact`, `deterministic_id`)
- `memory_engine/ontology.py` - fixed vocabulary (`EntityType`, `Predicate`), `OntologyVersion`, and `OntologyRegistry`
- `memory_engine/extractors.py` - pluggable Statement/Fact extraction logic and entity resolution
- `memory_engine/pipeline.py` - stage functions plus `MemoryCompiler`
- `memory_engine/patch.py` - Phase 2 MemoryPatch contract specifications (`MemoryReader`, `MemoryDelta`, `MemoryPatchLinker`)
- `docs/rfcs/` - formal Architecture RFCs (RFC 001, RFC 002)

See `docs/roadmap.md` for current phase status and progress.

