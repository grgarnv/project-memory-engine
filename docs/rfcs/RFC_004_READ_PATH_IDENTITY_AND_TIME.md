# RFC 004: The Read Path, Conditional Determinism, and Time

**Status:** APPROVED ARCHITECTURAL SPECIFICATION
**Scope:** Belief resolution, reproducibility qualification, temporal ordering, entity identity
**Supersedes:** nothing. Amends RFC 001 §Determinism and RFC 003 §2.

---

## 1. Why this RFC exists

RFCs 001–003 specify how artifacts enter memory. None of them specify how
anything comes out. The system had three approved write-side RFCs and zero read
paths, which meant its central claim — that a project can answer questions from
accumulated knowledge instead of document retrieval — had never been executed.

Building the smallest possible read path falsified four write-side assumptions
within a day. This RFC records what changed as a result. See
`docs/findings/read-path.md` for the experiment.

---

## 2. Belief resolution is core infrastructure, not an application

Roadmap Phase 3 listed an "Explanation Engine" as an application built on
memory. That placement was wrong. Resolving accumulated evidence into current
belief is neither compilation nor linking, and every application named in the
vision — explanation, compliance, onboarding, review — needs the same
resolution. If each builds its own, they will disagree with each other about
what the project believes.

`memory_engine.resolve` therefore sits as a sibling of `compiler` and `linker`,
not beneath them.

### 2.1 Read-side non-goals

Mirroring RFC 003 §6, the resolver will never:

1. **Call an LLM.** Resolution is deterministic traversal.
2. **Perform vector or embedding retrieval.** Resolution operates on bound
   entity IDs and recorded edges.
3. **Invent ranking heuristics at read time.** Weighting uses only values the
   linker stored. If a ranking input does not exist in memory, the answer omits
   the ranking rather than fabricating the input.
4. **Mutate memory.** Reading is side-effect free, and this is tested.
5. **Fabricate belief from absence.** "No entity by that name", "bound but never
   asserted", and "asserted under no decision predicate" are three distinct
   answers and must not collapse into one.

### 2.2 Read contracts are separate from write contracts

`MemoryReader` is the write-side contract: the minimal lookups a linker needs.
It does not expose object-position queries, superseded facts, supersession
edges, or evidence — all of which a resolver requires.

`BeliefReader` declares those separately. A store implements both. Keeping them
apart prevents the linker from acquiring read-path privileges and prevents the
resolver from acquiring the ability to write.

---

## 3. Determinism is conditional, and must be recorded

RFC 001 states that compiling the same artifact years later produces the same
semantic IR. As written that is false, and was false before the LLM extractor
existed: ontology versions evolve, and extractor configuration is pluggable.

**Amended invariant.** Compilation is deterministic given the tuple:

```
(artifact content, compiler version, ontology version, extractor configuration)
```

`CompiledArtifact` records `compiler_version` and `ontology_version` so a stored
compilation can be identified with the tuple that produced it. Re-compilation
under a different tuple is a *new* compilation, not a contradiction of the old
one, and memory treats it as additional evidence rather than a correction.

### 3.1 Compiler-local identity

RFC 003 §2 specifies deterministic local ordinals (`obs:0`, `seg:1`) for
transient compiler nodes. The implementation used UUIDs, which made the
reproducibility guarantee untestable — identical input produced different IR on
every run.

Local IDs are now ordinals assigned within a compilation scope. Outside a scope
(hand-constructed IR) they fall back to UUIDs.

---

## 4. Memory must carry time

### 4.1 The defect

Nothing in `PersistedFact`, `EvidenceRecord`, or `SupersessionEdge` carried a
timestamp. `SingleOccupancyDecisionRule` retired whatever was already in the
store when a new decision arrived. Consequence: replaying an identical corpus in
a different order inverted what the project believed — the decision with one
supporting artifact became current, and the decision with three became
superseded.

Append-only memory was monotonic in *content* but not in *meaning*. A backfill of
a ten-year repository, a re-index, or two ingestion workers racing would each
produce different beliefs from identical inputs.

### 4.2 The model

Time attaches to **evidence**, not to facts. A fact is not an event; it is a
claim about the world that artifacts support at points in time. `Artifact` gains
`recorded_at` (ISO-8601); `EvidenceRecord` carries it; a fact's assertion time is
derived as the maximum over its evidence.

### 4.3 Ordering

Every supersession decision routes through `compare_assertions`, yielding:

| Outcome | Meaning | Effect |
|---|---|---|
| `LATER` | incoming post-dates stored | incoming supersedes stored |
| `EARLIER` | incoming pre-dates stored | **stored supersedes incoming** |
| `SIMULTANEOUS` | equal timestamps, incompatible content | `ConflictEdge`; memory declines to pick |
| `UNKNOWN` | no usable timestamps | ingestion order, edge marked `basis="ingestion_order"` |

The `EARLIER` case is what makes backfill safe. The `UNKNOWN` case is not
silently equivalent to `LATER`: the basis is stored on the edge and reported by
the resolver, because a memory whose beliefs rest on replay order should say so
rather than look confident.

**Invariant.** For a corpus of timestamped artifacts, belief is invariant under
every ingestion permutation. Tested exhaustively per scenario.

---

## 5. Supersession must name its cause

`SupersessionEdge` recorded fact → fact and a reason string. Since a fact can
carry many evidence records, "ADR 012 retired the JWT decision" was not
recoverable — only "some fact supported by three artifacts retired it". The
explanation was missing its middle term.

`SupersessionEdge` now carries `source_artifact_id`, `recorded_at`, and `basis`.

---

## 6. Evidence must be weighable

`PersistencePass` wrote `confidence=1.0` on every evidence record, discarding the
compiler's claim confidence. An ADR and a commit message were indistinguishable,
so no future ranking work had any input to rank on.

Evidence now carries the claim's confidence, the artifact type, and that type's
authority (`ADR 1.0`, `CODE 0.9`, `PR 0.8`, `DOCUMENT 0.7`, `ISSUE 0.6`,
`COMMIT 0.5`, `SLACK 0.3`).

`BeliefNode.support` is the sum of `confidence × authority` across evidence.
**It is derived at read time and never stored, and it is explicitly not a
probability of truth** — it states how much the project has committed to a
belief, not how likely that belief is to be correct.

---

## 7. Entity identity hashes the name only

Global entity IDs previously hashed `(entity_type, canonical_name)`. Since
entity typing is a heuristic that varies by surrounding text, one artifact
calling OAuth2 a `FRAMEWORK` and another calling it a `FEATURE` produced two
permanently distinct entities in an append-only store.

Identity now hashes the normalized canonical name alone. Typing is a claim about
a thing, not a component of what it is.

**Unresolved.** This does not solve aliasing: `API Gateway`, `the gateway`, and
`APIGW` remain three identities. Merge semantics in an append-only store — where
IDs cannot be rewritten — is the next open identity problem. Candidate direction:
an explicit `SAME_AS` edge resolved at read time, so merging becomes an assertion
with evidence rather than a mutation. Not specified here.

---

## 8. What the linker consumes

`Relation` was computed by the compiler and never read by the linker, which
re-matched fact operands as strings. The linker now prefers the compiler's
resolved entity references when a `Relation` exists for a fact, falling back to
string binding otherwise.
