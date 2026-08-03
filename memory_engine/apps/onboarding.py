"""
Onboarding brief.

"What should someone new know about this project?" answered from accumulated
evidence rather than from whoever happens to be free to explain it.

The ordering principle throughout is support — how much the project has
committed to a belief — never recency alone and never alphabetical. A decision
three artifacts corroborate outranks one mentioned once in a commit message,
which is the ordering a person would use if they had read everything.

The brief includes what memory is *unsure* about. A new engineer is better
served by "these two things contradict and nobody resolved it" than by a tidy
summary that hides it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memory_engine.memory.contracts import BeliefReader
from memory_engine.memory.model import is_artifact_ref
from memory_engine.ontology import Predicate
from memory_engine.resolve.queries import ProjectQueries
from memory_engine.resolve.resolver import BeliefResolver


@dataclass
class OnboardingBrief:
    decisions: list[tuple[str, str, float]] = field(default_factory=list)
    constraints: list[tuple[str, str]] = field(default_factory=list)
    key_components: list[tuple[str, int]] = field(default_factory=list)
    superseded: list[tuple[str, str]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines: list[str] = []

        if self.decisions:
            lines.append("CURRENT DECISIONS")
            for subject, obj, support in self.decisions:
                lines.append(f"  {subject}: {obj}   (support {support})")
            lines.append("")

        if self.constraints:
            lines.append("RULES THE PROJECT HOLDS")
            for subject, obj in self.constraints:
                lines.append(f"  {subject} must not use {obj}")
            lines.append("")

        if self.key_components:
            lines.append("MOST-REFERENCED COMPONENTS")
            for label, count in self.key_components:
                lines.append(f"  {label}   ({count} facts)")
            lines.append("")

        if self.superseded:
            lines.append("WHAT CHANGED (superseded decisions)")
            for subject, obj in self.superseded:
                lines.append(f"  {subject} used to be {obj}")
            lines.append("")

        if self.open_questions:
            lines.append("WHAT MEMORY IS UNSURE ABOUT")
            lines.extend(f"  ! {q}" for q in self.open_questions)

        return "\n".join(lines).rstrip() or "Memory is empty."


def brief(reader: BeliefReader, all_facts, limit: int = 10) -> OnboardingBrief:
    resolver = BeliefResolver(reader)
    queries = ProjectQueries(reader)
    result = OnboardingBrief()

    mentions: dict[str, int] = {}

    for fact in all_facts:
        for ref in (fact.subject_ref, fact.object_ref):
            if ref.startswith("entity_"):
                mentions[ref] = mentions.get(ref, 0) + 1

        if is_artifact_ref(fact.subject_ref):
            continue

        subject = reader.label_for_ref(fact.subject_ref)
        obj = reader.label_for_ref(fact.object_ref)
        superseded = reader.is_superseded(fact.id)

        if fact.predicate is Predicate.SELECTED:
            if superseded:
                result.superseded.append((subject, obj))
            else:
                support = round(
                    sum(e.weight for e in reader.evidence_for_fact(fact.id)), 6
                )
                result.decisions.append((subject, obj, support))
        elif fact.predicate is Predicate.PROHIBITS and not superseded:
            result.constraints.append((subject, obj))

    result.decisions.sort(key=lambda d: (-d[2], d[0]))
    result.constraints.sort()
    result.superseded.sort()
    result.decisions = result.decisions[:limit]

    result.key_components = sorted(
        ((reader.label_for_ref(ref), count) for ref, count in mentions.items()),
        key=lambda pair: (-pair[1], pair[0]),
    )[:limit]

    health = queries.health(all_facts)
    result.open_questions = list(health.notes)
    if health.open_conflicts:
        result.open_questions.append(
            f"{health.open_conflicts} contradiction(s) recorded and unresolved."
        )
    return result
