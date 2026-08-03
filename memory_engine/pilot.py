"""
Pilot measurement.

A pilot without a definition of success is a demo. This measures the only thing
that matters: given questions people actually asked, how many does memory answer
correctly, how many does it answer wrongly, and how many does it decline?

The middle number is the one to watch. A system that says "I don't know" is
usable. A system that is confidently wrong is worse than nothing, because it
costs trust that the correct answers then have to buy back.

    questions.json:
    {"questions": [
       {"ask": "service-to-service authentication", "expect": "OAuth2"},
       {"ask": "session storage", "expect": "PostgreSQL"},
       {"ask": "rate limiting", "expect": null}
    ]}

`expect: null` means the project has no recorded position, and answering it is a
FALSE answer, not a success. Including a few of these is what stops the metric
rewarding a system that confidently answers everything.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from memory_engine.memory.contracts import BeliefReader
from memory_engine.resolve import BeliefResolver


@dataclass(slots=True)
class QuestionResult:
    ask: str
    expected: str | None
    got: str | None
    outcome: str  # "correct" | "wrong" | "declined" | "correctly_declined"

    @property
    def is_harmful(self) -> bool:
        """Wrong answers are the expensive failure; declining is not."""
        return self.outcome == "wrong"


@dataclass
class PilotReport:
    results: list[QuestionResult] = field(default_factory=list)

    def _count(self, outcome: str) -> int:
        return sum(1 for r in self.results if r.outcome == outcome)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def correct(self) -> int:
        return self._count("correct") + self._count("correctly_declined")

    @property
    def wrong(self) -> int:
        return self._count("wrong")

    @property
    def declined(self) -> int:
        return self._count("declined")

    @property
    def coverage(self) -> float:
        """Share of questions memory attempted at all."""
        return (self.total - self.declined) / self.total if self.total else 0.0

    @property
    def accuracy_when_answered(self) -> float:
        answered = self.total - self.declined
        return (self.correct - self._count("correctly_declined")) / answered if answered else 0.0

    def render(self) -> str:
        lines = [
            f"questions           {self.total}",
            f"correct             {self.correct}",
            f"wrong               {self.wrong}",
            f"declined            {self.declined}",
            f"coverage            {self.coverage:.0%}",
            f"accuracy answered   {self.accuracy_when_answered:.0%}",
            "",
        ]
        for result in self.results:
            mark = {"correct": "ok  ", "wrong": "WRONG", "declined": "  - ",
                    "correctly_declined": "ok  "}[result.outcome]
            lines.append(f"  {mark} {result.ask}"
                         f"  expected={result.expected}  got={result.got}")
        if self.wrong:
            lines.append("")
            lines.append(
                "Wrong answers are the number to drive to zero first. A system "
                "that declines is usable; one that is confidently wrong is not."
            )
        return "\n".join(lines)


def run_pilot(reader: BeliefReader, questions_path: str | Path) -> PilotReport:
    spec = json.loads(Path(questions_path).read_text())
    resolver = BeliefResolver(reader)
    report = PilotReport()

    for question in spec["questions"]:
        ask = question["ask"]
        expected = question.get("expect")
        belief = resolver.explain(ask)
        decision = belief.decision
        got = decision.object_label if decision else None

        if got is None:
            outcome = "correctly_declined" if expected is None else "declined"
        elif expected is None:
            outcome = "wrong"  # answered where memory should have had no position
        elif got.strip().lower() == expected.strip().lower():
            outcome = "correct"
        else:
            outcome = "wrong"

        report.results.append(QuestionResult(ask, expected, got, outcome))

    return report
