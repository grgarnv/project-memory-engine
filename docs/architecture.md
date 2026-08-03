# Architecture

Project Memory Engine turns software artifacts (PRs, commits, ADRs, issues) into
a persistent, append-only model of what a project knows about itself.

Three components, in strict dependency order. Each answers a different question.

| Component | Question | State |
|---|---|---|
| Compiler | What does *this artifact* assert? | stateless |
| Linker | How does that assertion enter memory? | stateful |
| Resolver | What does the project *currently believe*, and why? | read-only |

The resolver is core infrastructure, not an application. Explanation engines,
compliance engines, and onboarding assistants are built on top of it — they are
not it. See RFC 004 §2.

---

## Dependency direction

```
        ontology  <----------------  ir  <----------------  compiler
            ^                                                  |
            |                                                  | (no edge)
            |                                                  X
            |                                                  |
          memory  <---- linker                                 v
            ^   ^                                        CompiledArtifact
            |   +------- store
            |
          resolve
```

| Package | May import |
|---|---|
| `ontology` | — |
| `ir` | `ontology` |
| `compiler` | `ir`, `ontology` |
| `memory` | `ontology` |
| `linker` | `ir`, `memory` |
| `store` | `memory` |
| `resolve` | `memory` |
| `ingest` | all of the above |

`memory` is the spine. The linker writes its types, the resolver reads them,
stores implement its contracts — so neither side depends on the other. The
compiler never imports the linker; the resolver never imports either.

`tests/test_import_boundaries.py` parses every module's AST and fails the build
if any of this stops being true. These are assertions, not conventions.

---

## Compiler

```
Artifact
   |
   v
observe()              -> Observation   typed paragraphs, section headers preserved
   |
   v
segment()              -> Segment       description / reason / decision / tradeoff / ...
   |
   +--> extract_statements()  -> Statement   (subject, predicate, target)
   |         |
   |         v
   |     extract_claims()     -> Claim       confidence-scored assertion
   |         |
   |         v
   |     extract_facts()      -> Fact        ontology-normalized, filtered
   |         |
   |         v
   |     resolve_entities()   -> ResolvedFact
   |         |
   |         v
   |     extract_relations()  -> Relation    Entity --predicate--> Entity
   |
   +--> extract_entities()    -> Entity      named things
```

Entity extraction is a parallel branch off Segment, not downstream of Fact: it
needs the sentence, not the triple.

`MemoryCompiler.compile()` runs every stage in order and returns a typed
`CompiledArtifact`. Nothing runs outside `compile()`.

### Statement extraction is composite

Two extractors run, and they are not redundant:

- **`RuleBasedStatementExtractor`** — segment kind → artifact-level assertion.
  Subject is always the artifact. Preserves what the document said.
- **`RelationalStatementExtractor`** — surface patterns → domain assertion.
  Subject and object are project concepts. This is what makes the graph a graph.

A system with only the first can answer "what does ADR 012 say", which is
document retrieval with extra steps. A system with only the second loses the
document's own voice.

Both the relational extractor and `PhraseEntityRecognizer` read the same pattern
table (`compiler/extractors/patterns.py`), so a phrase can never become a fact
operand without also existing as an entity.

### Claim vs Fact

Deliberately separate IR types:

- **Claim** — epistemic IR. Anything the artifact asserts, scored by a hedge-word
  heuristic. May be vague or wrong; that is fine.
- **Fact** — normalized ontology IR. A Claim that cleared
  `FACT_CONFIDENCE_THRESHOLD` *and* mapped onto a known `Predicate`. Unmapped
  predicates are dropped, never invented.

---

## Linker

```
CompiledArtifact
   |
   v
BindingPass         local entities -> global IDs; $ARTIFACT_SELF -> ArtifactRef
   |
   v
PersistencePass     facts -> content-addressed PersistedFact + EvidenceRecord
   |
   v
AnalysisPipeline    composable rules -> SupersessionEdge / ConflictEdge
   |
   v
MemoryDelta         append-only; contains no deletions
```

Rules, run in order and then de-duplicated:

- `ExplicitDeprecationRule` — "replace X with Y" retires facts naming X as current
- `SingleOccupancyDecisionRule` — a new `SELECTED` on the same subject retires the old
- `DirectNegationConflictRule` — `PROHIBITS` vs `ALLOWS` becomes a recorded conflict

Every supersession routes through `linker/ordering.py`, never through arrival
order. See "Time" below.

---

## Resolver

```
ProjectMemory
   |
   v
BeliefResolver.explain(entity)
   |
   v
ResolvedBelief
   current       active facts, with accumulated evidence and support
   history       superseded facts, with the edge and artifact that retired them
   conflicts     contradictions memory declined to resolve
   diagnostics   why this answer is incomplete or fragile
```

Deterministic traversal, no synthesis. Walks supersession edges in both
directions — a current decision is only half an answer without what it replaced.

Distinguishes three kinds of "no": name unknown, name bound but never asserted,
and asserted only under non-decision predicates. Collapsing those would be
fabrication.

---

## Core invariants

1. **Conditional determinism.** Compilation is reproducible given
   `(content, compiler version, ontology version, extractor config)`.
   `CompiledArtifact` records the versions. Compiler-local IDs are ordinals
   (`obs:0`, `stmt:3`), not UUIDs — otherwise the guarantee is untestable.
2. **Content-addressed identity.** Artifacts hash `(type, content)`; entities hash
   the normalized name **only**, never the type, so two artifacts disagreeing about
   an entity's type still bind to one entity; facts hash `(subject, predicate, object)`;
   evidence hashes `(artifact, source fact)`.
3. **One PersistedFact → many EvidenceRecords.** N artifacts asserting the same
   relationship accumulate evidence under one node.
4. **Evidence is weighable.** Each record carries claim confidence, artifact type,
   and that type's authority. `support` is derived at read time and never stored.
   It measures commitment, not probability of truth.
5. **Append-only.** No `UPDATE`, no `DELETE` in any store. Invalidation is a
   `SupersessionEdge`, which names the artifact that caused it.
6. **Order-independent belief.** Any ingestion permutation of a timestamped corpus
   converges on the same belief.
7. **Ontology separation.** `ArtifactRef` keeps evidence documents out of the
   domain concept namespace.
8. **No LLM below the compiler.** The provider abstraction is quarantined in
   `compiler/extractors/llm/` and the boundary test forbids importing it elsewhere.

---

## Time

Time attaches to **evidence**, not to facts. A fact is not an event; it is a claim
about the world that artifacts support at points in time. A fact's assertion time
is derived as the maximum `recorded_at` over its evidence.

`compare_assertions` yields four outcomes:

| Outcome | Effect |
|---|---|
| `LATER` | incoming supersedes stored |
| `EARLIER` | **stored supersedes incoming** — this is what makes backfill safe |
| `SIMULTANEOUS` | `ConflictEdge`; memory declines to pick |
| `UNKNOWN` | ingestion order, edge marked `basis="ingestion_order"` |

`UNKNOWN` is not silently equivalent to `LATER`. The basis is stored on the edge
and reported in the answer, because a memory whose beliefs rest on replay order
should say so rather than look confident.

---

## Modules

| Path | Contents |
|---|---|
| `ontology.py` | `EntityType`, `Predicate`, `OntologyVersion`, `OntologyRegistry` |
| `ir.py` | compiler IR, `deterministic_id`, `local_id_scope` |
| `compiler/pipeline.py` | stage functions + `MemoryCompiler` |
| `compiler/extractors/patterns.py` | relational pattern table, phrase normalization |
| `compiler/extractors/{statements,facts,entities,relations}.py` | pluggable extraction |
| `compiler/extractors/llm/` | provider abstraction (quarantined) |
| `memory/model.py` | `PersistedFact`, `EvidenceRecord`, `SupersessionEdge`, `ConflictEdge`, `MemoryDelta`, `ArtifactRef` |
| `memory/contracts.py` | `MemoryReader` / `BeliefReader` / `MemoryWriter` / `ProjectMemory` |
| `linker/passes/` | binding, persistence, analysis |
| `linker/rules/` | deprecation, single-occupancy, negation |
| `linker/ordering.py` | temporal comparison |
| `store/in_memory.py` | reference implementation |
| `store/sqlite.py` | durable store |
| `resolve/resolver.py` | `BeliefResolver`, `ResolvedBelief`, `BeliefNode` |
| `resolve/render.py` | presentation only |
| `ingest.py` | the only module wiring all three components |
| `cli.py` | `compile` / `ingest` / `ask` / `stats` |

See `docs/roadmap.md` for phase status, `docs/rfcs/` for the formal
specifications, and `docs/findings/read-path.md` for what building the read path
exposed.
