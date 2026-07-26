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
   |         +--> extract_facts()   -> Fact   (ontology-normalized)
   |         +--> extract_claims()  -> Claim  (confidence-scored)
   |
   +--> extract_entities()    -> Entity  (named things mentioned)
```

`MemoryCompiler.compile()` in `memory_engine/pipeline.py` runs every stage
above in order and returns all of it (observations, segments, statements,
entities, facts, claims) in one dict. There is no stage that runs but isn't
called from `compile()` - if it's in the file, it's in the pipeline.

## Modules

- `memory_engine/ir.py` - every data type the pipeline passes around
- `memory_engine/ontology.py` - the fixed vocabulary (`EntityType`, `Predicate`)
  that free text gets normalized into
- `memory_engine/extractors.py` - pluggable Statement/Fact extraction logic
  (currently rule-based; `LLMStatementExtractor` is a documented stub for
  Phase 1)
- `memory_engine/pipeline.py` - the stage functions plus `MemoryCompiler`

## What's deliberately not here yet

- **Project Memory / storage** - persisting facts across multiple artifacts
  over time. Nothing here yet; this is Phase 2.
- **MemoryPatch** - the diff you'd apply to long-term memory when new facts
  arrive. The dataclass exists in `ir.py`; nothing produces one yet.
- **Explanation Engine / Compliance Engine** - Phase 3, not started.

See `docs/roadmap.md` for what's actually done vs. planned.
