# Project Memory Engine

A software project accumulates knowledge for years across PRs, commits, ADRs,
RFCs, issues, and design discussions — and then has to search it, every time,
from scratch.

The project has history. It does not have understanding.

This is an attempt to give a project a persistent internal model of itself: what
was decided, what replaced what, why, and on what evidence. Not a retrieval
system with a language model in front of it — a compiler and a linker that build
knowledge incrementally, and a resolver that answers from what was accumulated.

```
$ pme ingest fixtures/scenarios/oauth2-supersedes-jwt --ask "service-to-service authentication"

Q: what does the project believe about 'service-to-service authentication'?

CURRENT
  service-to-service authentication --selected--> OAuth2
    support=2.3 across 3 artifact(s)  last asserted 2024-06-03
      adr          2024-05-02   weight=1.0    artifact=artifact_e38077af3bd
      pull_request 2024-05-20   weight=0.8    artifact=artifact_a64b97b1092
      commit       2024-06-03   weight=0.5    artifact=artifact_b128cf09d80

SUPERSEDED
  service-to-service authentication --selected--> JWT
    support=1.0 across 1 artifact(s)  last asserted 2023-01-11
      adr          2023-01-11   weight=1.0    artifact=artifact_df702710a63
    retired by fact_b92e2d38ef1f2ec (Single-occupancy decision supersession; basis=recorded_at)
      via artifact artifact_e38077af3bd
```

No LLM produced that answer. No document was retrieved to produce it. Four
markdown files were compiled into semantic IR, linked into an append-only graph,
and resolved.

Status: **early research prototype.** The extraction layer is deliberately naive;
the architecture around it is the point.

---

## Quickstart

```bash
git clone <this repo> && cd project-memory-engine
pip install -e ".[dev]"
pytest                                     # 247 tests, ~4s

pme ingest fixtures/scenarios/oauth2-supersedes-jwt --ask "service-to-service authentication"
pme compile fixtures/artifacts/sample_adr.md
pme eval                    # extraction precision and recall against labels
```

Ask it questions in prose, or query the graph directly:

```bash
pme ingest fixtures/eval/queue-consolidation --db project.db
pme explain "asynchronous messaging" --db project.db
pme timeline RabbitMQ      --db project.db
pme dependents Kafka       --db project.db
pme health                 --db project.db
pme brief                  --db project.db   # onboarding overview
pme check "order service|uses|RabbitMQ" --db project.db
pme migrate --to 1.0       --db project.db   # ontology impact, dry by construction
```

```
$ pme explain "asynchronous messaging" --db project.db

The project uses Kafka for asynchronous messaging. That position is asserted by
an ADR, most recently on 2024-11-12.

This replaced an earlier position: uses RabbitMQ for asynchronous messaging,
asserted by an ADR, most recently on 2022-08-01. It was retired by artifact
artifact_0c77e2b.
```

Persist to disk and query later:

```bash
pme ingest fixtures/scenarios/oauth2-supersedes-jwt --db project.db
pme ask "OAuth2" --db project.db
pme stats --db project.db
```

---

## The idea

**A compiler Fact is not truth. It is evidence.**

When an ADR says "use OAuth2 for service-to-service authentication", that is one
artifact's assertion. When a PR and a commit say the same thing, memory does not
store three facts — it stores one fact with three evidence records. Knowledge is
accumulated evidence, and that distinction drives everything else in the design.

**Memory is append-only.** A decision is never overwritten. It is retired by a
`SupersessionEdge` that records which fact replaced it, which artifact caused the
replacement, and whether the ordering came from timestamps or from ingestion
order. "What did we believe in 2023 and why" stays answerable forever.

**The compiler never knows history.** It turns one artifact into IR, statelessly
and reproducibly. Everything about identity, accumulation, and time lives in the
linker. Compiling an artifact in 2034 produces the same IR as compiling it today,
given the same compiler and ontology version.

---

## Architecture

```
    Artifact                              CompiledArtifact
       |                                        |
       v                                        v
   [ COMPILER ]  stateless                  [ LINKER ]  stateful
       |                                        |
   observe                                  BindingPass      entities -> global IDs
   segment                                  PersistencePass  facts + evidence
   extract_statements                       AnalysisPipeline supersession, conflicts
   extract_entities                             |
   extract_claims                               v
   extract_facts                            MemoryDelta
   resolve_entities                             |
   extract_relations                            v
       |                                  [ PROJECT MEMORY ]  append-only
       v                                        |
   CompiledArtifact                             v
                                           [ RESOLVER ]  read path
                                                |
                                                v
                                          ResolvedBelief
                                            current / history / evidence /
                                            conflicts / diagnostics
```

| Package | Role | May import |
|---|---|---|
| `ontology` | fixed vocabulary, versioned registry | — |
| `ir` | compiler intermediate representation | `ontology` |
| `compiler` | artifact → IR, stateless | `ir`, `ontology` |
| `memory` | persistent schema + store contracts | `ontology` |
| `linker` | IR → memory delta, stateful | `ir`, `memory` |
| `store` | in-memory and SQLite implementations | `memory` |
| `resolve` | memory → belief | `memory` |
| `apps` | compliance, onboarding | `resolve` |
| `eval` | extraction scoring | `ingest`, `store` |
| `ingest` | the wiring | all |

The compiler never imports the linker. The resolver never imports either. That is
not a convention — `tests/test_import_boundaries.py` walks the AST of every module
and fails the build if it stops being true.

### Layers in detail

**Compiler** — `Artifact → Observation → Segment → Statement → Claim → Fact`, with
`Segment → Entity` and `Fact + Entity → Relation`. A Claim is anything the artifact
asserts, scored for hedging. A Fact is a Claim that cleared the confidence
threshold *and* mapped onto a known ontology predicate. Unmapped predicates are
dropped, never invented.

**Linker** — three deterministic passes. Binding resolves local entity mentions to
content-addressed global IDs (hashed on name only, so two artifacts disagreeing
about an entity's *type* still land on one entity). Persistence promotes facts to
content-addressed nodes and attaches evidence. Analysis runs composable rules that
emit supersession and conflict edges.

**Resolver** — the read path. Walks supersession edges in both directions and
gathers evidence. Performs no synthesis: where memory has no answer it says so,
and it distinguishes "never heard of it" from "know the name, never became
knowledge."

---

## Invariants

These are tested, not aspirational.

1. **Reproducible compilation** — identical output for identical
   `(content, compiler version, ontology version, extractor config)`. Compiler-local
   IDs are deterministic ordinals (`obs:0`, `stmt:3`), never UUIDs.
2. **Content-addressed identity** — artifacts, entities, facts, and evidence all
   have stable hash IDs, so re-ingesting anything is a no-op rather than a duplicate.
3. **One fact, many evidence records** — the same assertion from N artifacts never
   duplicates the graph node.
4. **Nothing is ever deleted** — no `UPDATE`, no `DELETE` anywhere in the SQLite
   store; a test asserts this against the module's SQL literals.
5. **Order-independent belief** — ingesting a corpus in any order converges on the
   same belief. Every permutation of every scenario is tested. Where timestamps are
   missing, the fallback is recorded as `basis="ingestion_order"` and surfaced in
   the answer rather than hidden.
6. **No LLM below the compiler** — the provider abstraction is quarantined in
   `compiler/extractors/llm/`, and the boundary test forbids importing it from the
   linker, stores, or resolver.

---

## Explicitly out of scope

No vector databases, no graph databases, no embeddings, no agent loops, no MCP, no
orchestration frameworks. None of those answer the open question, which is whether
a project can build and justify knowledge about itself deterministically.

An LLM extractor is supported behind the `StatementExtractor` interface — it
changes how well statements are found, not the shape of what memory stores.

---

## Layout

```
memory_engine/
  ontology.py            vocabulary + versioned registry
  ir.py                  compiler IR, deterministic and local identity
  compiler/              stateless artifact -> IR
    pipeline.py
    extractors/          statements, facts, entities, relations, patterns
      llm/               provider abstraction (quarantined)
  memory/                persistent schema + store contracts
    model.py             PersistedFact, EvidenceRecord, SupersessionEdge, ...
    contracts.py         MemoryReader / BeliefReader / MemoryWriter
  linker/                stateful IR -> delta
    passes/              binding, persistence, analysis
    rules/               deprecation, single-occupancy, negation
    ordering.py          time comparison; the fix for order-dependent belief
  store/                 in_memory.py, sqlite.py
  resolve/               resolver.py, render.py
  ingest.py              compiler + linker + store, wired
  cli.py

docs/
  architecture.md, roadmap.md, changelog.md
  rfcs/                  RFC 001-004
  findings/read-path.md  what building the read path exposed

fixtures/
  artifacts/             single artifacts
  scenarios/             multi-artifact stories + expected_belief.json

tests/
  compiler/ linker/ store/ resolve/ contracts/ scenarios/
  test_import_boundaries.py
```

---

## Running it on a real project

```bash
pme pull github://your-org/your-repo --db project.db   # PRs, issues, review threads
pme pull git://.                     --db project.db   # commit messages
pme pull docs/adr                    --db project.db   # ADRs

pme serve --db project.db                              # MCP, six tools
pme pilot questions.json --db project.db               # measure the pilot
pme correct fact_a1b2 --author you --reason "never adopted" --db project.db
```

Incremental: each source keeps a watermark, so a nightly run reads only what is
new. Sub-millisecond queries at 40k facts. Corrections are append-only artifacts
that retire a fact without deleting anything. Full guide in
`docs/deployment.md`.

## Extraction quality

Extraction is measured, not estimated. `pme eval` scores the engine's output
against triples labelled from the documents:

| Case | Precision | Recall (reachable) | F1 |
|---|---|---|---|
| auth-migration | 100% | 100% | 100% |
| queue-consolidation | 100% | 100% | 100% |
| hard-realistic | 100% | 25% | 40% |
| **total** | **100%** | **84%** | **91%** |

`hard-realistic` is adversarial on purpose — conversational decisions, rejections
buried in subordinate clauses, and an unimplemented action item that must *not*
become a fact. It scores badly, and it exists so the suite cannot report a
saturated 100%.

Labels deliberately include assertions the pattern table cannot reach, so recall
reports the real gap rather than a flattering one. The harness earned its place
on first run by catching a precision gate that scored 100% precision and 38%
recall because one head noun was missing from a closed vocabulary — invisible
from reading the output, since everything that came through was correct.

Caveat stated plainly in `docs/findings/extraction-evaluation.md`: both corpora
were written by the same person who wrote the extractor. These numbers show
regression, not capability.

## Roadmap

See `docs/roadmap.md`. Next: compound-sentence splitting, an independently
labelled corpus, and ontology evolution.

The test every proposal has to pass:

> **Does this strengthen the project's ability to build, preserve, justify, and
> evolve software knowledge over time?**

If not, it probably does not belong in the core.
