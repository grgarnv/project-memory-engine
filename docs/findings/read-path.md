# Findings: building the first read path

**Status:** findings 1–7 closed, plus two more surfaced during the fix.
Kept as a record of why the architecture changed, not as an open issue list.

---

## The experiment

The system had three approved write-side RFCs and zero read paths. Its central
claim — that a project can answer questions from accumulated knowledge rather
than document retrieval — had never once been executed.

So: build the smallest thing that answers *"Why do we use OAuth2 instead of
JWT?"* end to end from persistent memory. Not an explanation engine. A function
returning a struct.

Three runs against a four-artifact corpus (ADR 004 chooses JWT, ADR 012 replaces
it with OAuth2, PR 318 implements it, commit 9a1 removes the old keys):

| Run | Compiler | Linker | Resolver | Answered? |
|---|---|---|---|---|
| A | real | real | real | **no** — memory held nothing about OAuth2 or JWT |
| B | stubbed extraction | real | real | **yes** — full answer with provenance |
| C | stubbed extraction, artifacts reordered | real | real | **yes, but inverted** |

Run B proved the architecture below the extractor was sound. Runs A and C were
the findings.

---

## Findings

### 1. The compiler emitted no entity-anchored facts — CLOSED

`RuleBasedStatementExtractor` hardcoded `subject=CURRENT_CHANGE` and put the
entire segment text in `target`. Every persisted fact looked like:

```
artifact:artifact_e38077af --selected--> 'Use OAuth2 for service-to-service authentication.'
```

Subject was the artifact. Object was a paragraph. Four entities were recognized,
bound to global IDs, stored — and appeared in **zero** facts. Entities and facts
were two disjoint graphs, and no question about a *concept* was answerable.

**Fix.** `RelationalStatementExtractor` plus a shared pattern table that also
feeds `PhraseEntityRecognizer`, so an operand cannot exist without its entity.
Both artifact-level and domain-level extraction now run; they are not redundant.

### 2. `Relation` was computed and discarded — CLOSED

Every artifact compiled to `relations=0`, and the linker read only
`compiled_artifact.facts`. The Phase 2 headline item never reached memory.

**Fix.** `PersistencePass` prefers the compiler's resolved entity references when
a `Relation` exists for a fact.

### 3. Fact deduplication could not fire — CLOSED

With `subject_ref = artifact:<id>` and `object_ref` a verbatim paragraph, no two
artifacts could produce the same content-addressed ID. Run A: 13 facts, 13
evidence records, strict 1:1. The evidence model — the project's stated core
idea — had never been exercised.

**Fix.** Follows from 1. Three artifacts now accumulate on one decision node.

### 4. Supersession could not fire — CLOSED

Both decision rules keyed on `get_active_facts_for_subject`. Since every
artifact's facts were anchored to its own `ArtifactRef`, two artifacts never
shared a subject. Run A: ADR 012 explicitly replaces ADR 004, and memory recorded
**0 supersessions**.

**Fix.** Follows from 1. `ExplicitDeprecationRule` additionally retires facts
naming the deprecated thing in *object* position, which needed a new
`get_active_facts_with_object` query on the reader contract.

### 5. Memory carried no time, so supersession direction was ingestion order — CLOSED

The one that did not follow from finding 1, and the one that mattered most.

Nothing in `PersistedFact`, `EvidenceRecord`, or `SupersessionEdge` carried a
timestamp. `SingleOccupancyDecisionRule` retired whatever was already in the
store. Run C fed the identical four artifacts in a different order:

```
CURRENT     service-to-service authentication --selected--> JWT      (1 artifact)
SUPERSEDED  service-to-service authentication --selected--> OAuth2   (3 artifacts)
```

The project believed the thing with one supporting artifact and had retired the
thing with three. Append-only memory was monotonic in content but not in
meaning: a backfill, a re-index, or two ingestion workers racing would each
produce different beliefs from identical inputs.

**Fix.** Time attaches to evidence. All supersession routes through
`compare_assertions`, which supersedes the *incoming* fact when it pre-dates the
stored one. Equal timestamps with incompatible content become a conflict rather
than a coin flip. Missing timestamps fall back to ingestion order and record
`basis="ingestion_order"`, which the resolver surfaces.

**Verified.** All 24 permutations of the scenario converge on one belief;
asserted per scenario in `tests/scenarios/`.

### 6. Supersession had no provenance — CLOSED

The edge recorded fact → fact and a reason string. Since a fact can carry many
evidence records, "ADR 012 retired the JWT decision" was unrecoverable — only
"some fact supported by three artifacts retired it". The explanation was missing
its middle term.

**Fix.** `SupersessionEdge` carries `source_artifact_id`, `recorded_at`, `basis`.

### 7. Evidence confidence was a hardcoded literal — CLOSED

`PersistencePass` wrote `confidence=1.0` on every record, discarding the
compiler's claim confidence. An ADR and a commit message weighed identically, so
future ranking work had nothing to rank on.

**Fix.** Evidence carries claim confidence, artifact type, and type authority.
`BeliefNode.support` is derived at read time and never stored — and is explicitly
*not* a probability of truth. It states how much the project has committed to a
belief.

---

## Surfaced while fixing the above

### 8. Compiler-local IDs were UUIDs — CLOSED

RFC 003 §2 specifies deterministic local ordinals (`obs:0`, `seg:1`). The
implementation used `uuid4`, so compiling the same artifact twice produced
different IR and the reproducibility guarantee was not testable. Caught by a
test written for a different purpose.

**Fix.** `local_id_scope` in `ir.py`; ordinals inside a compilation, UUID
fallback outside.

### 9. The two stores disagreed about idempotency — CLOSED

The store conformance suite caught this on the day it was written:
`InMemoryProjectMemory` grew its evidence list when a delta was replayed, while
SQLite's `INSERT OR IGNORE` made it a no-op.

**Fix.** In-memory store dedupes by content-addressed ID. This is the argument
for a shared conformance suite rather than per-store tests — the divergence was
invisible until both ran the same assertions.

---

## Still open

**Entity aliasing.** Identity now hashes the canonical name only, so type
disagreement no longer forks an entity. But `API Gateway`, `the gateway`, and
`APIGW` remain three permanent identities in a store where IDs cannot be
rewritten. Merge semantics in append-only memory is the next identity problem.
Candidate direction: an explicit `SAME_AS` edge resolved at read time, making a
merge an assertion with evidence rather than a mutation.

**Confidence semantics.** The hedge-word heuristic measures assertiveness of
phrasing, not likelihood of truth. It is isolated in one function
(`_score_confidence`) so replacing it touches one place.

**Extraction coverage.** The relational pattern table is a floor, not a ceiling.
An LLM extractor implementing `StatementExtractor` can replace it without any
change below the compiler — what matters architecturally is the *shape* of the
output, `(entity, predicate, entity)`, not the sophistication of the matcher.

---

## Method note

The read path was worth building before the disk engine specifically because it
was cheap to be wrong: nothing was persisted, so there was no schema to migrate
and no corpus to reprocess. Findings 5, 6, and 7 are all schema-shaped. Each
would have become a migration if SQLite had landed first.

In a system whose premise is "the project already knows", the read path is not
the application layer. It is the proof.
