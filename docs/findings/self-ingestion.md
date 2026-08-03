# Findings: pointing the engine at its own repository

**Method.** The scenario fixtures were written by someone who knew the pattern
table, so they measure nothing. This run ingests documents nobody wrote for the
engine: the four RFCs, the findings, the architecture doc, the roadmap, the
changelog, the README, and the commit log. `scripts/ingest_repo.py`.

**Headline.** The ranking in the previous roadmap was wrong. Aliasing was
listed as the next problem; on a real corpus it is not a problem at all yet,
because almost nothing reaches the graph for it to fragment.

---

## Run 1 — baseline

| Metric | Value |
|---|---|
| artifacts | 11 |
| persisted facts | 176 |
| **domain-anchored** | **4 (2.3%)** |
| artifact-scoped `describes` | 172 |
| entity name clusters | 1 (and only from a fixture) |

Three of the four domain facts were garbage:

```
and no corpus     --uses--------> reprocess
so neither side   --depends_on--> other
so neither        --depends_on--> other
```

Two findings, in order of severity.

### Finding A — a pattern match is not evidence that its operands are concepts

The captures were clause fragments. Nothing checked whether "and no corpus"
could denote anything. Precision was roughly 25%.

**Fix.** An operand qualifies only if it looks technical (contains an uppercase
letter or digit) or its head noun is domain vocabulary, and never if it opens
with a conjunction, pronoun, modal, or determiner. Trailing modals are trimmed,
because "The compiler never imports" captures "compiler never" otherwise.

### Finding B — patterns ran against whole paragraphs

One match per pattern per paragraph shadowed the rest, and a capture could span
a sentence boundary. Matching is now sentence-by-sentence.

### Finding C — markdown was parsed as prose

Code fences and table rows became `describes` facts carrying whole code blocks
and matrices. Bullet lists collapsed into one fact for what the author wrote as
several. `observe()` now strips fences and table rows and expands bullets.

### Finding D — negation was silently dropped

"The compiler never imports the linker" produced nothing. That is a rule the
project holds, and dropping it loses a real fact — while inverting it into
`imports` would fabricate one. A negated *currency* predicate (`uses`,
`imports`, `calls`, `depends_on`, `requires`, `contains`) now yields
`PROHIBITS`, which is what the ontology already had for it. Negating anything
else is still dropped rather than inverted.

---

## Run 2 — after the fixes

| Metric | Before | After |
|---|---|---|
| domain facts | 4 | 2 |
| of which correct | 1 | **2** |
| precision | ~25% | **100%** |
| junk operands | 3 | 0 |

Both survivors are real:

```
ADR 004   --replaced_by--> ADR 012
compiler  --prohibits----> linker
```

The second was extracted from prose in `architecture.md` and is a genuine
architectural constraint the project holds.

---

## The open problem: recall

Two facts from eleven documents is not a knowledge graph.

**The honest reading is that the corpus is wrong, not only the extractor.** The
engine targets decision records — ADRs, PRs, commits — where sentences assert
relationships between named things. RFCs and architecture docs are mostly
definitional and normative prose: "memory is the spine", "the resolver reads
these types", "identity now hashes the canonical name alone". Few of those are
`(entity, predicate, entity)` under any predicate the ontology has.

So this run measured precision well and recall badly, because the corpus was the
least relational one in the repository. Two things follow, and they should not be
conflated:

1. **Precision work is done and is measurable.** The gates are tested against the
   exact strings that produced junk.
2. **Recall is unmeasured.** It needs a corpus of real ADRs and PRs from a
   project that was not built around this engine, with a hand-labelled subset so
   precision and recall are numbers rather than impressions.

## What this changes about sequencing

- **Aliasing drops down the list.** It is a real problem, but it is a problem
  about graphs that are dense enough to fragment. There is no evidence yet that
  this one is.
- **A labelled evaluation corpus moves to the top.** Every extraction decision
  from here is otherwise made on anecdote. This is the same argument as building
  the read path before the disk engine: measure the thing before optimizing it.
- **Ontology gaps become visible only after that.** "The linker writes these
  types" has no predicate. Whether that matters is an empirical question, and
  right now nobody can answer it.
