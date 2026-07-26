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
above in order and returns all of it (observations, segments, statements,
claims, facts, entities) in one dict. There is no stage that runs but
isn't called from `compile()` - if it's in the file, it's in the pipeline.

## Claim vs. Fact

These are deliberately not the same thing:

- **Claim** - anything the artifact asserts. Every `Statement` becomes
  exactly one `Claim`. May be wrong, vague, or hedged - that's fine, it's
  just a claim. Confidence is scored by a placeholder heuristic (hedge/modal
  word match - see `pipeline._score_confidence`).
- **Fact** - a `Claim` that `FactPass` (`RuleBasedFactExtractor` in
  `extractors.py`) has accepted as structured knowledge. Promoted only if
  both hold:
  - confidence >= `FACT_CONFIDENCE_THRESHOLD` (concrete enough)
  - predicate maps to a known ontology `Predicate` (structured enough)

  Otherwise the claim stays a Claim only - it is not dropped, just not
  promoted. Each `Fact` keeps `source_claim` pointing back to the `Claim`
  it came from, which itself keeps `supporting_statements` pointing back
  to the originating `Statement`(s) - a full provenance chain.

See `tests/golden/pr_003_hedged/` for a golden case that proves a hedged
claim is correctly *not* promoted.

## Modules

- `memory_engine/ir.py` - every data type the pipeline passes around
- `memory_engine/ontology.py` - the fixed vocabulary (`EntityType`, `Predicate`)
  that free text gets normalized into
- `memory_engine/extractors.py` - pluggable Statement/Fact extraction logic
  (currently rule-based; `LLMStatementExtractor` is a documented stub for
  Phase 1)
- `memory_engine/pipeline.py` - the stage functions plus `MemoryCompiler`

## What's deliberately not here yet

- **Relation** - an Entity-to-Entity edge (e.g. API Gateway --uses--> JWT
  validation). This needs entity resolution first: nothing currently links
  a Fact's subject/object text to the separately-extracted Entity list.
  That linking step, not the `Relation` dataclass itself, is the real next
  design question - see `docs/roadmap.md`.
- **Project Memory / storage** - persisting facts across multiple artifacts
  over time. Nothing here yet; this is Phase 2.
- **MemoryPatch** - the diff you'd apply to long-term memory when new facts
  arrive. The dataclass exists in `ir.py`; nothing produces one yet.
- **Explanation Engine / Compliance Engine** - Phase 3, not started.

See `docs/roadmap.md` for what's actually done vs. planned.
