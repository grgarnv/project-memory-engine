"""
Compliance engine.

The project records constraints: `PROHIBITS` facts, extracted from sentences
like "the compiler never imports the linker" and "the order service must not use
RabbitMQ". Those are rules the project holds, sitting in memory with evidence
and dates attached.

This checks proposed or observed relationships against them, and — because the
constraints came from artifacts — every violation can name the document that
established the rule and when. A compliance report that cannot cite its own
authority is just an opinion with a red icon.

Two things it deliberately does not do:

  - It does not treat the absence of a constraint as permission. "No rule
    forbids this" is reported as unknown, not as compliant, because memory's
    silence is not consent.
  - It does not check superseded constraints. A rule that was retired is not a
    rule, and reporting it would make the report untrustworthy in exactly the
    cases where people most need to trust it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memory_engine.memory.contracts import BeliefReader
from memory_engine.ontology import Predicate
from memory_engine.resolve.identity import IdentityResolver


@dataclass(slots=True)
class Violation:
    """A proposed relationship that an active constraint forbids."""
    subject: str
    predicate: Predicate
    object: str
    constraint_fact_id: str
    established_by: list[str] = field(default_factory=list)
    established_at: str = ""
    support: float = 0.0

    def describe(self) -> str:
        when = f" ({self.established_at})" if self.established_at else ""
        sources = ", ".join(a[:16] for a in self.established_by) or "no recorded artifact"
        return (
            f"{self.subject} {self.predicate.value} {self.object} "
            f"is forbidden by a constraint established in {sources}{when}"
        )


@dataclass
class ComplianceReport:
    checked: int = 0
    violations: list[Violation] = field(default_factory=list)
    unknown: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_compliant(self) -> bool:
        """No violations found. Not the same as 'everything was verified'."""
        return not self.violations

    def summary(self) -> str:
        lines = [
            f"checked {self.checked} relationship(s): "
            f"{len(self.violations)} violation(s), "
            f"{len(self.unknown)} with no applicable rule"
        ]
        lines.extend(f"  VIOLATION  {v.describe()}" for v in self.violations)
        if self.unknown:
            lines.append(
                "  Memory holds no rule about the remainder. That is an absence "
                "of evidence, not permission."
            )
        return "\n".join(lines)


# Asserting any of these is asserting use.
_USE_PREDICATES = (
    Predicate.USES, Predicate.DEPENDS_ON, Predicate.REQUIRES,
    Predicate.IMPORTS, Predicate.CALLS, Predicate.SELECTED,
)


class ComplianceEngine:
    def __init__(self, reader: BeliefReader):
        self.reader = reader
        self.identity = IdentityResolver(reader)

    def constraints_for(self, subject_name: str) -> list:
        """Active PROHIBITS facts about a subject, across its identity class."""
        ref = self.reader.resolve_ref(subject_name)
        if ref is None:
            return []

        found = []
        for member in self.identity.equivalence_class(ref).refs:
            for fact in self.reader.facts_mentioning(member):
                if fact.predicate is not Predicate.PROHIBITS:
                    continue
                if fact.subject_ref != member:
                    continue
                if self.reader.is_superseded(fact.id):
                    continue  # a retired rule is not a rule
                found.append(fact)
        return found

    def check(self, proposed: list[tuple[str, Predicate, str]]) -> ComplianceReport:
        """
        Check proposed relationships against recorded constraints.

        `proposed` is whatever the caller can observe — a dependency manifest,
        an import graph, a design doc's claims. The engine supplies the rules,
        not the observations.
        """
        report = ComplianceReport()

        for subject, predicate, obj in proposed:
            report.checked += 1
            if predicate not in _USE_PREDICATES:
                report.unknown.append((subject, predicate.value, obj))
                continue

            obj_ref = self.reader.resolve_ref(obj)
            obj_class = (
                set(self.identity.equivalence_class(obj_ref).refs) if obj_ref else set()
            )

            matched = False
            for constraint in self.constraints_for(subject):
                if constraint.object_ref not in obj_class:
                    continue
                evidence = self.reader.evidence_for_fact(constraint.id)
                report.violations.append(Violation(
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    constraint_fact_id=constraint.id,
                    established_by=[e.source_artifact_id for e in evidence],
                    established_at=max((e.recorded_at for e in evidence if e.recorded_at),
                                       default=""),
                    support=round(sum(e.weight for e in evidence), 6),
                ))
                matched = True

            if not matched:
                report.unknown.append((subject, predicate.value, obj))

        return report
