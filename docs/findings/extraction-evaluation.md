# Findings: measuring extraction instead of eyeballing it

Every extraction decision before this was made on impression: run it, read the
output, form a view. That is how the pattern table reached ~25% precision
without anyone noticing.

`memory_engine/eval/` compares the engine's domain facts against triples a
careful reader labelled from the documents. `pme eval`.

## Current numbers

| Case | Precision | Recall (reachable) | F1 |
|---|---|---|---|
| auth-migration | 100% | 100% | 100% |
| queue-consolidation | 100% | 75% | 86% |
| **total** | **100%** | **87%** | **93%** |

"Reachable" excludes labels marked `known_unreachable` — assertions the pattern
table is not expected to catch. Both figures are reported, because a label set
containing only reachable triples would report 100% recall and hide the gap.

## What the harness caught immediately

**A closed vocabulary was destroying recall.** The precision gate added in the
previous round accepted a lowercase phrase only if its head noun was in a fixed
domain list. First eval run: **100% precision, 38% recall**, and every single
miss was the phrase "web tier" — because `tier` was not in the list.

That is the entire argument for the harness. Reading the output would not have
shown it; the facts that *did* come through were all correct, so it looked fine.
A closed vocabulary silently fails on every project that names things
differently, and the failure is invisible from the inside.

The gate now has a third rule: a multi-word phrase with no grammatical filler in
it qualifies. Recall went 38% → 88% on that case with precision unchanged.

**A label of mine was wrong.** The extractor read "the analytics pipeline
already runs on Kafka" as `depends_on`; I had labelled it `uses`. On review the
extractor was right. The label is corrected and the correction is recorded in
`labels.json`, so it is not mistaken later for tuning the test to fit the code.

## What is still missed, and why

```
notification worker --uses--> Kafka
order consumer      --uses--> Kafka
order service       --prohibits--> RabbitMQ
```

1. **Compound sentences.** "The order service uses Kafka, and the notification
   worker uses Kafka" yields one fact. Sentence splitting handles `.` but not
   coordinated clauses.
2. **Title-derived assertions.** "Port the order consumer to Kafka" is a title;
   the concept is the object of a verb the table has no pattern for.
3. **Verb inflection.** `must not use RabbitMQ` misses because the pattern
   requires `uses`.

All three are cheap to fix. I have deliberately not fixed them in the same pass
that established the baseline — tuning against your own eval in the run that
creates it is how a harness becomes a mirror.

## On the floors in `tests/eval/`

`MIN_PRECISION = 0.85`, `MIN_RECALL = 0.60`, both set *below* current numbers.
They catch regression without requiring an edit every time extraction improves.
Raising them to whatever the extractor currently scores would make the suite
agree with the code by construction.

## The honest limitation

Both cases were written by the same person who wrote the extractor. That is
better than fixtures written *around* the pattern table, but it is not
independent. The next real measurement needs ADRs and PRs from a project that
has never heard of this engine, labelled by someone who has not read
`patterns.py`. Until then these numbers show regression, not capability.
