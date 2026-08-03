"""
Human corrections.

The first week of real use will produce wrong facts. Nothing in the system so
far lets a person say "that's wrong", and that gap is the one most likely to
kill adoption: a single visibly wrong answer costs more trust than ten right
ones earn.

Append-only already implies the mechanism. A correction is an ARTIFACT — it has
an author, a timestamp, and evidential weight, exactly like an ADR. Retracting a
fact is therefore not a deletion and not a special case: it is a supersession
edge attributed to a correction artifact, using machinery that already exists.

Three consequences worth stating, because each one is a design choice rather
than a fallout:

  1. Corrections are queryable history. "Who said this was wrong, and when"
     survives, which matters when the correction itself turns out to be wrong.
  2. A correction can be superseded. If a later artifact reasserts the fact with
     better evidence, the normal ordering rules apply.
  3. A correction outranks documents for RETRACTION only. It carries the highest
     authority in the table, but retract() is the only thing it can drive - a
     person disputing a fact does not thereby get to make architectural
     decisions by fiat.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from memory_engine.ir import ARTIFACT_AUTHORITY, Artifact, ArtifactType, deterministic_id
from memory_engine.memory.model import (
    EvidenceRecord,
    MemoryDelta,
    PersistedFact,
    SupersessionEdge,
)
from memory_engine.ontology import Predicate


@dataclass(slots=True)
class Correction:
    """A person's claim that memory holds something wrong."""
    fact_id: str
    author: str
    reason: str
    recorded_at: str = ""
    replacement_object: str = ""  # optional: "it's actually X"

    def __post_init__(self) -> None:
        if not self.recorded_at:
            self.recorded_at = date.today().isoformat()

    @property
    def artifact(self) -> Artifact:
        content = (
            f"Correction by {self.author}: fact {self.fact_id} is incorrect. "
            f"{self.reason}"
        )
        if self.replacement_object:
            content += f" The correct value is {self.replacement_object}."
        return Artifact(
            id=deterministic_id("artifact", "correction", content),
            type=ArtifactType.CORRECTION,
            content=content,
            recorded_at=self.recorded_at,
            metadata={"author": self.author, "corrects": self.fact_id},
        )


class CorrectionError(ValueError):
    pass


def retract(memory, correction: Correction) -> MemoryDelta:
    """
    Retire a fact on a person's authority.

    Produces an ordinary MemoryDelta. The fact is not touched, not rewritten,
    and not removed — it is superseded by the correction artifact, and stays
    fully queryable as history.
    """
    target = memory.get_fact(correction.fact_id)
    if target is None:
        raise CorrectionError(f"No fact with id {correction.fact_id!r}")
    if memory.is_superseded(correction.fact_id):
        raise CorrectionError(
            f"Fact {correction.fact_id} is already superseded; correcting it "
            f"again would record a retraction of something already retired."
        )

    artifact = correction.artifact
    delta = MemoryDelta(artifact_id=artifact.id, artifact_recorded_at=artifact.recorded_at)

    # The correction is itself an assertion about the artifact, so it carries
    # evidence like anything else. Without this the supersession would have a
    # cause but no support.
    marker = PersistedFact(
        id=deterministic_id("fact", f"artifact:{artifact.id}", "describes", correction.fact_id),
        subject_ref=f"artifact:{artifact.id}",
        predicate=Predicate.DESCRIBES,
        object_ref=correction.fact_id,
        fact_type="observation",
    )
    delta.promoted_facts.append(marker)
    delta.evidence_records.append(EvidenceRecord(
        id=deterministic_id("evidence", artifact.id, marker.id),
        persisted_fact_id=marker.id,
        source_artifact_id=artifact.id,
        source_fact_id=marker.id,
        artifact_type=ArtifactType.CORRECTION.value,
        recorded_at=correction.recorded_at,
        confidence=1.0,
        authority=ARTIFACT_AUTHORITY[ArtifactType.CORRECTION],
        supporting_statements=[],
    ))

    delta.supersessions.append(SupersessionEdge(
        superseding_fact_id=marker.id,
        superseded_fact_id=correction.fact_id,
        reason=f"Corrected by {correction.author}: {correction.reason}",
        source_artifact_id=artifact.id,
        recorded_at=correction.recorded_at,
        basis="human_correction",
    ))

    delta.diagnostics.append(
        f"fact {correction.fact_id} retracted on human authority; the fact and "
        f"its evidence remain queryable as history"
    )
    return delta


def apply_correction(memory, correction: Correction) -> MemoryDelta:
    """Retract and persist in one step."""
    delta = retract(memory, correction)
    memory.apply_delta(delta)
    return delta
