# Contributing

## The test every change has to pass

> Does this strengthen the project's ability to build, preserve, justify, and
> evolve software knowledge over time?

If not, it probably does not belong in the core. Applications go on top of the
resolver, not inside it.

## Setup

```bash
pip install -e ".[dev]"
pytest
```

## Boundaries

`tests/test_import_boundaries.py` enforces the dependency direction by parsing
every module's AST. If it fails, the fix is almost never to relax the test:

- The **compiler** may import `ir` and `ontology`. Nothing about memory or history.
- The **linker** talks to `MemoryReader`, never to a concrete store.
- The **resolver** reads the schema and knows nothing about how facts got there.
- The **schema** (`memory/`) imports no layer at all — both sides depend on it.
- Nothing below the compiler may import `compiler/extractors/llm/`.

## Adding a store

Implement `ProjectMemory` and add it to the `any_store` fixture in
`tests/conftest.py`. The conformance suite runs against every store; a store is
not allowed its own definition of correct behaviour. That suite has already
caught one divergence the individual stores' tests missed.

## Adding an analysis rule

Subclass `AnalysisRule`, append edges to the delta, mutate nothing else. Route
every supersession through `record_supersession` so ordering stays temporal
rather than arrival-based — a rule that appends a `SupersessionEdge` directly
reintroduces the defect RFC 004 §4 exists to fix.

## Adding extraction

Implement `StatementExtractor`. What matters architecturally is the *shape* of
the output — `(entity, predicate, entity)` — not the sophistication of the
matcher. If a phrase can be a fact operand it must also be recognized as an
entity, or the linker binds to a raw string and the concept never enters the
graph.

## Regenerating goldens

Compiler goldens (`tests/compiler/golden/*/expected.json`) and scenario beliefs
(`fixtures/scenarios/*/expected_belief.json`) are checked in deliberately.
Regenerate them only when a behaviour change is intended, and say so in the
changelog — a silently regenerated golden is a deleted test.

## Memory semantics

Append-only is not a convention. No `UPDATE`, no `DELETE`, in any store, ever.
Invalidation is a `SupersessionEdge`. If a change seems to need mutation, the
memory model is being violated rather than the store lacking a feature.
