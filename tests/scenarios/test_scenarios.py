"""
Scenario goldens: the regression test for what the project actually claims to do.

The compiler goldens pin IR for one artifact. These pin the BELIEF that a whole
corpus produces - the only test that fails if the system stops answering its
own motivating question.

Each scenario directory holds artifacts, a manifest with types and timestamps,
and expected_belief.json.
"""
import itertools
import json
from pathlib import Path

import pytest

from memory_engine.ingest import Ingestor
from memory_engine.ir import ArtifactType
from memory_engine.resolve import BeliefResolver, render
from memory_engine.store import InMemoryProjectMemory, SQLiteProjectMemory
from tests.conftest import SCENARIOS

SCENARIO_DIRS = sorted(p for p in SCENARIOS.iterdir() if (p / "expected_belief.json").exists())


def _resolve(memory, directory: Path):
    Ingestor(memory=memory).ingest_scenario(directory)
    expected = json.loads((directory / "expected_belief.json").read_text())
    return BeliefResolver(memory).explain(expected["query"]), expected


@pytest.mark.parametrize("directory", SCENARIO_DIRS, ids=lambda p: p.name)
def test_scenario_produces_the_expected_belief(directory):
    belief, expected = _resolve(InMemoryProjectMemory(), directory)

    assert belief.decision is not None
    assert belief.decision.object_label == expected["current_decision"]
    assert belief.decision.support == pytest.approx(expected["current_support"])
    assert sorted(e.artifact_type for e in belief.decision.evidence) == \
        expected["current_evidence_artifact_types"]
    assert sorted(n.object_label for n in belief.history) == expected["superseded"]
    assert sorted({n.retirement_basis for n in belief.history}) == expected["supersession_basis"]
    assert len(belief.conflicts) == expected["conflicts"]


@pytest.mark.parametrize("directory", SCENARIO_DIRS, ids=lambda p: p.name)
def test_scenario_is_invariant_across_ingestion_order(directory):
    """
    Every permutation of the corpus must converge on the same belief. This is
    the property that makes backfilling a decade of history safe.
    """
    manifest = json.loads((directory / "manifest.json").read_text())["artifacts"]
    expected = json.loads((directory / "expected_belief.json").read_text())

    outcomes = set()
    for order in itertools.permutations(manifest):
        memory = InMemoryProjectMemory()
        ingestor = Ingestor(memory=memory)
        for entry in order:
            ingestor.ingest_file(
                directory / entry["file"],
                ArtifactType(entry["type"]),
                entry.get("recorded_at", ""),
            )
        belief = BeliefResolver(memory).explain(expected["query"])
        outcomes.add((
            belief.decision.object_label if belief.decision else None,
            tuple(sorted(n.object_label for n in belief.history)),
            belief.decision.support if belief.decision else None,
        ))

    assert len(outcomes) == 1, f"ingestion order changed the answer: {outcomes}"


@pytest.mark.parametrize("directory", SCENARIO_DIRS, ids=lambda p: p.name)
def test_scenario_answer_is_identical_on_sqlite(directory, tmp_path):
    """Durable memory must believe exactly what in-process memory believes."""
    in_memory, _ = _resolve(InMemoryProjectMemory(), directory)
    store = SQLiteProjectMemory(tmp_path / "scenario.db")
    try:
        on_disk, _ = _resolve(store, directory)
        assert render(on_disk) == render(in_memory)
    finally:
        store.close()


@pytest.mark.parametrize("directory", SCENARIO_DIRS, ids=lambda p: p.name)
def test_scenario_survives_a_reopen(directory, tmp_path):
    """Memory that does not survive the process is not memory."""
    db = tmp_path / "persisted.db"
    expected = json.loads((directory / "expected_belief.json").read_text())

    store = SQLiteProjectMemory(db)
    Ingestor(memory=store).ingest_scenario(directory)
    store.close()

    reopened = SQLiteProjectMemory(db)
    try:
        belief = BeliefResolver(reopened).explain(expected["query"])
        assert belief.decision.object_label == expected["current_decision"]
        assert sorted(n.object_label for n in belief.history) == expected["superseded"]
    finally:
        reopened.close()
