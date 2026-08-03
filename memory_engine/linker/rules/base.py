"""Analysis rule interface and shared helpers."""
from __future__ import annotations

from abc import ABC, abstractmethod

from memory_engine.linker.ordering import Order, basis_for, compare_assertions
from memory_engine.memory.contracts import MemoryReader
from memory_engine.memory.model import ConflictEdge, MemoryDelta, SupersessionEdge


class AnalysisRule(ABC):
    """
    One independent, composable analysis. Runs like a compiler optimization
    pass: reads memory plus the delta, appends supersession or conflict edges,
    never mutates facts or evidence.
    """

    name: str = "rule"

    @abstractmethod
    def analyze(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        ...


def record_supersession(
    reader: MemoryReader,
    delta: MemoryDelta,
    incoming_fact_id: str,
    stored_fact_id: str,
    reason: str,
) -> None:
    """
    Register that one of these two facts retires the other, in whichever
    direction the timestamps say - not in the direction they happened to
    arrive.

    Simultaneous assertions with different content are a conflict, not a
    supersession: memory records the disagreement and declines to pick.
    """
    incoming_at = delta.artifact_recorded_at
    stored_at = reader.latest_evidence_time(stored_fact_id)
    order = compare_assertions(incoming_at, stored_at)

    if order is Order.SIMULTANEOUS:
        delta.conflicts.append(
            ConflictEdge(
                fact_a_id=stored_fact_id,
                fact_b_id=incoming_fact_id,
                conflict_type="simultaneous_incompatible_assertions",
                source_artifact_id=delta.artifact_id,
            )
        )
        return

    if order is Order.EARLIER:
        superseding, superseded = stored_fact_id, incoming_fact_id
        reason = f"{reason} (incoming assertion pre-dates stored assertion)"
    else:
        superseding, superseded = incoming_fact_id, stored_fact_id

    delta.supersessions.append(
        SupersessionEdge(
            superseding_fact_id=superseding,
            superseded_fact_id=superseded,
            reason=reason,
            source_artifact_id=delta.artifact_id,
            recorded_at=incoming_at,
            basis=basis_for(order),
        )
    )
