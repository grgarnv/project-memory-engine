# Deploying on a real project

Everything below exists and is tested. Two prerequisites are not, and cannot be,
satisfied from inside this repository — they are listed last, honestly.

## 1. Pull from where decisions actually live

```bash
pme pull git://path/to/repo        --db project.db   # commit messages
pme pull docs/adr                  --db project.db   # ADRs and RFCs
pme pull github://your-org/your-repo --db project.db # PRs and issues, with review threads
```

Incremental by construction. Each source records a watermark, so a nightly run
reads only what appeared since the last one. Artifact IDs are content-addressed,
so an overlap is a no-op — the watermark is an optimisation, not a correctness
mechanism. That is why a rewritten git history safely falls back to a full read.

`git` watermarks on SHA rather than date, because commit dates are not monotonic
across merges and a date cursor silently skips work.

GitHub auth comes from `GITHUB_TOKEN` in the environment and is never a function
argument, so it cannot end up in a log line or a stack trace. Rate limits are
retried with backoff off the `X-RateLimit-Reset` header.

**Dates matter more than they look.** A directory of ADRs with no per-file dates
gives every artifact the same timestamp, and simultaneous incompatible decisions
become recorded conflicts rather than a supersession chain. `FilesystemSource`
reads the first commit that added each file for exactly this reason. If your
documents are not in git, supply dates in a manifest.

## 2. Expect wrong facts, and make correcting them cheap

The first week will produce wrong facts. One visibly wrong answer costs more
trust than ten right ones earn, so the correction path has to be as easy as the
read path.

```bash
pme correct fact_a1b2c3 --author arnav --reason "ADR 019 was never adopted" --db project.db
```

A correction is an **artifact**: it has an author, a date, and evidential
weight, and it retires the fact through the same supersession machinery
everything else uses. Nothing is deleted. The fact stays queryable, the
correction is itself queryable, and if the correction later turns out to be
wrong it can be superseded in turn.

Corrections carry the highest authority in the table (1.2, above an ADR's 1.0),
but they can only drive retraction. A person disputing a fact does not thereby
get to make architectural decisions by fiat.

## 3. Put it where people already are

```bash
pme serve --db project.db     # MCP over stdio
```

Six tools: `ask_project`, `project_timeline`, `project_dependents`,
`check_constraint`, `project_brief`, `correct_fact`. Read-only except the last,
and there is deliberately no deletion tool — a test asserts none exists.

## 4. Measure the pilot

```bash
pme pilot questions.json --db project.db
```

```json
{"questions": [
  {"ask": "session storage", "expect": "PostgreSQL"},
  {"ask": "rate limiting",   "expect": null}
]}
```

`expect: null` means the project has no recorded position. Answering it counts
as **wrong**, not as coverage. Include several — without them the metric rewards
a system that confidently answers everything, which is the failure mode that
matters.

Three numbers come out. Drive **wrong** to zero first. A system that declines is
usable; one that is confidently wrong is not, because it spends trust the
correct answers then have to buy back.

## 5. Scale

Query cost at 40,000 facts on SQLite:

| Query | Per call |
|---|---|
| `facts_mentioning` | 0.03 ms |
| `identity_closure` | 0.06 ms |
| `find_existing_fact` | 0.01 ms |

`facts_mentioning` is a `UNION` of two indexed lookups rather than an `OR` —
SQLite will not use two indices for a single `OR` predicate and falls back to a
full scan. The identity closure is one recursive CTE instead of a query per
alias. A test asserts 100 lookups over 20,000 facts complete in under a second,
so a regression to linear scanning fails the build rather than showing up in
production.

## 6. LLM extraction, when you get there

`CachedLLMStatementExtractor` keeps RFC 004 §3 true. Every extraction is keyed on
`(segment text, model, prompt version, temperature, provider)` and cached
durably, so:

- two runs of the same configuration produce identical IR without a second model
  call
- re-compiling an archive costs nothing after the first pass, which is what makes
  an LLM extractor affordable at repository scale at all
- changing the model changes the key; old entries are kept, not invalidated. A
  model upgrade is a **new compilation**, and memory already knows how to hold
  two assertions from different sources — that is the evidence model. An upgrade
  lands as additional evidence, never as a rewrite.

`CompiledArtifact.metadata["extractor"]` records the fingerprint, so a stored
compilation can always be identified with the configuration that produced it.

---

## The two things that cannot be finished from here

**The answerability check.** Before any of the above, take 30 real ADRs and PRs
from your repository and 20 questions your team actually asked, and hand-check
what fraction are answerable *in principle* — by you, reading them. If it is
60%, this is worth deploying. If it is 15%, the problem is that your decisions
live in people's heads and meeting calls, and no compiler recovers what was
never written down. Two days, and it is the only item here that can invalidate
the rest.

**Independent extraction labels.** `pme eval` reports 100% precision and 84%
reachable recall, and those numbers demonstrate absence of regression rather
than capability, because the labels and the extractor share an author. Real
measurement needs a corpus from a project that has never heard of this engine,
labelled by someone who has not read `patterns.py`. That is structural, not a
matter of remaining effort.
