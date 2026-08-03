"""
Extraction evaluation.

Every extraction decision so far has been made on anecdote: run it, eyeball the
output, form an impression. That is how the pattern table ended up with 25%
precision without anyone noticing.

This harness makes precision and recall numbers. A case is a directory of
artifacts plus `labels.json` — the triples a careful reader says the documents
assert. The engine's domain facts are compared against them.

Two properties the labels must have to be worth anything:

  1. They are written from the DOCUMENTS, not from the engine's output.
     Labelling whatever the extractor produced measures nothing.
  2. They include assertions the current patterns cannot reach. A label set
     that only contains reachable triples reports 100% recall and hides the
     gap. Recall below 100% is the point.

Matching is on normalized (subject, predicate, object). Case-insensitive, since
casing is a presentation concern; otherwise exact, because a near-miss operand
is a wrong fact, not a partial credit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from memory_engine.ingest import Ingestor
from memory_engine.ir import ArtifactType
from memory_engine.memory.model import is_artifact_ref
from memory_engine.store import InMemoryProjectMemory

Triple = tuple[str, str, str]


def _norm(triple: Triple) -> Triple:
    return tuple(part.strip().lower() for part in triple)  # type: ignore[return-value]


@dataclass
class EvalCase:
    name: str
    directory: Path
    labels: list[Triple]
    notes: str = ""
    unreachable: list[Triple] = field(default_factory=list)
    forbidden: list[Triple] = field(default_factory=list)
    floor: dict = field(default_factory=lambda: {"precision": 0.85, "reachable_recall": 0.60})

    @property
    def reachable_labels(self) -> list[Triple]:
        """Labels not marked as known-out-of-reach for the current extractor."""
        unreachable = {_norm(t) for t in self.unreachable}
        return [t for t in self.labels if _norm(t) not in unreachable]


@dataclass
class Scores:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def __add__(self, other: "Scores") -> "Scores":
        return Scores(
            self.true_positives + other.true_positives,
            self.false_positives + other.false_positives,
            self.false_negatives + other.false_negatives,
        )


@dataclass
class EvalResult:
    case: EvalCase
    predicted: list[Triple]
    overall: Scores
    reachable: Scores
    matched: list[Triple] = field(default_factory=list)
    spurious: list[Triple] = field(default_factory=list)
    missed: list[Triple] = field(default_factory=list)
    violations: list[Triple] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """No forbidden triple was produced. This is pass/fail, not a score."""
        return not self.violations


def load_case(directory: str | Path) -> EvalCase:
    directory = Path(directory)
    spec = json.loads((directory / "labels.json").read_text())
    return EvalCase(
        name=spec.get("name", directory.name),
        directory=directory,
        labels=[tuple(t) for t in spec["labels"]],
        notes=spec.get("notes", ""),
        unreachable=[tuple(t) for t in spec.get("known_unreachable", [])],
        forbidden=[tuple(t) for t in spec.get("must_not_extract", [])],
        floor=spec.get("floor", {"precision": 0.85, "reachable_recall": 0.60}),
    )


def load_cases(root: str | Path) -> list[EvalCase]:
    root = Path(root)
    return [
        load_case(d) for d in sorted(root.iterdir())
        if d.is_dir() and (d / "labels.json").exists()
    ]


def _predicted_triples(memory) -> list[Triple]:
    """Domain facts only. Artifact-scoped assertions are not knowledge claims."""
    out = []
    for fact in memory.facts.values():
        if is_artifact_ref(fact.subject_ref):
            continue
        out.append((
            memory.label_for_ref(fact.subject_ref),
            fact.predicate.value,
            memory.label_for_ref(fact.object_ref),
        ))
    return sorted(set(out))


def run_case(case: EvalCase) -> EvalResult:
    memory = InMemoryProjectMemory()
    Ingestor(memory=memory).ingest_scenario(case.directory)

    predicted = _predicted_triples(memory)
    pred_set = {_norm(t) for t in predicted}
    label_set = {_norm(t) for t in case.labels}
    reachable_set = {_norm(t) for t in case.reachable_labels}

    matched = sorted(pred_set & label_set)
    spurious = sorted(pred_set - label_set)
    missed = sorted(label_set - pred_set)

    overall = Scores(
        true_positives=len(matched),
        false_positives=len(spurious),
        false_negatives=len(missed),
    )
    reachable = Scores(
        true_positives=len(pred_set & reachable_set),
        false_positives=len(spurious),
        false_negatives=len(reachable_set - pred_set),
    )

    forbidden_set = {_norm(t) for t in case.forbidden}
    violations = sorted(pred_set & forbidden_set)

    return EvalResult(
        case=case,
        violations=[t for t in violations],
        predicted=predicted,
        overall=overall,
        reachable=reachable,
        matched=[t for t in matched],
        spurious=[t for t in spurious],
        missed=[t for t in missed],
    )


def run_all(root: str | Path) -> list[EvalResult]:
    return [run_case(case) for case in load_cases(root)]


def format_report(results: list[EvalResult]) -> str:
    lines: list[str] = []
    total_overall = Scores()
    total_reachable = Scores()

    for result in results:
        total_overall = total_overall + result.overall
        total_reachable = total_reachable + result.reachable
        s, r = result.overall, result.reachable
        lines.append(f"{result.case.name}")
        lines.append(
            f"  overall    P={s.precision:.0%}  R={s.recall:.0%}  F1={s.f1:.0%}"
            f"   ({s.true_positives} hit / {s.false_positives} spurious"
            f" / {s.false_negatives} missed)"
        )
        lines.append(
            f"  reachable  P={r.precision:.0%}  R={r.recall:.0%}  F1={r.f1:.0%}"
        )
        if result.violations:
            lines.append("  FORBIDDEN TRIPLES PRODUCED:")
            lines.extend(f"    ! {s0} --{p}--> {o}" for s0, p, o in result.violations)
        if result.spurious:
            lines.append("  spurious:")
            lines.extend(f"    - {s0} --{p}--> {o}" for s0, p, o in result.spurious)
        if result.missed:
            lines.append("  missed:")
            lines.extend(f"    - {s0} --{p}--> {o}" for s0, p, o in result.missed)
        lines.append("")

    lines.append("=" * 60)
    lines.append(
        f"TOTAL overall    P={total_overall.precision:.0%}  "
        f"R={total_overall.recall:.0%}  F1={total_overall.f1:.0%}"
    )
    lines.append(
        f"TOTAL reachable  P={total_reachable.precision:.0%}  "
        f"R={total_reachable.recall:.0%}  F1={total_reachable.f1:.0%}"
    )
    return "\n".join(lines)
