# Project Memory Engine

A compiler-based system that transforms software artifacts into an evolving
model of project understanding.

```
Artifact -> Observation -> Segment -> Statement -> Fact / Claim
                                          |
                                          +-> Entity
```

Status: 🚧 early research prototype. See `docs/architecture.md` for how the
pieces fit together and `docs/roadmap.md` for what's done vs. planned.

## Quickstart

```bash
pip install -r requirements.txt
PYTHONPATH=. python cli.py
```

Runs the pipeline against `samples/sample_pr.md` and prints the resulting
observations, segments, statements, entities, facts, and claims.

## Tests

```bash
PYTHONPATH=. pytest -v
```

Golden-file tests live in `tests/golden/<case>/` as an `input.md` /
`expected.json` pair. Add a new case by dropping in both files - the suite
picks up every directory under `tests/golden/` automatically. `expected.json`
can optionally include `"fact_count": N` to also assert how many Claims get
promoted to Facts (see `tests/golden/pr_003_hedged` for a case that asserts
`0` - a hedged claim that should *not* be promoted).

## Layout

```
memory_engine/
    ir.py           all pipeline data types
    ontology.py     fixed EntityType / Predicate vocabulary
    extractors.py   pluggable Statement/Fact extraction logic
    pipeline.py     the stage functions + MemoryCompiler
samples/            example artifacts
tests/
    golden/         input/expected pairs, auto-discovered
docs/               architecture + roadmap
```
