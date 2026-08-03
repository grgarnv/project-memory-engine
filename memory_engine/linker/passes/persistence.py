"""
Pass 2: Persistence.

Promotes compiler Facts to content-addressed PersistedFact nodes and records
one EvidenceRecord per (artifact, fact). When two artifacts assert the same
relationship, the second adds evidence to the existing node - it does not
duplicate the node. That is the whole evidence model: knowledge is accumulated
evidence.

Two things this pass does that the first version did not:

  1. It consumes Relations. When the compiler resolved both operands of a fact
     to entities, the linker binds through those resolved entity IDs instead of
     re-matching strings.
  2. It carries real evidence metadata - the compiler's claim confidence, the
     artifact's timestamp, and the artifact type's authority - instead of
     writing a hardcoded 1.0. Nothing downstream can weigh evidence it was
     never given.
"""
from __future__ import annotations

from memory_engine.ir import ARTIFACT_AUTHORITY, CompiledArtifact, deterministic_id
from memory_engine.linker.passes.binding import BindingResult
from memory_engine.memory.contracts import MemoryReader
from memory_engine.memory.model import EvidenceRecord, MemoryDelta, PersistedFact

# The artifact talking about itself, in the compiler's vocabulary.
_SELF_REFERENCES = frozenset({"current change", "$artifact_self"})


class PersistencePass:
    def persist(
        self,
        reader: MemoryReader,
        compiled: CompiledArtifact,
        binding: BindingResult,
    ) -> MemoryDelta:
        artifact = compiled.artifact
        artifact_ref = binding.artifact_ref.as_ref()

        delta = MemoryDelta(
            artifact_id=artifact.id,
            artifact_recorded_at=artifact.recorded_at,
            bound_entities=binding.bound_list,
        )

        if not artifact.recorded_at:
            delta.diagnostics.append(
                "artifact has no recorded_at; any supersession it causes will "
                "be ordered by ingestion, not by time"
            )

        relation_by_fact = {r.source_fact_id: r for r in compiled.relations}
        authority = ARTIFACT_AUTHORITY.get(artifact.type, 0.5)
        promoted_in_this_delta: dict[str, PersistedFact] = {}

        for fact in compiled.facts:
            subject_ref = self._resolve_operand(
                fact.subject, binding, artifact_ref, relation_by_fact, fact.id, "subject"
            )
            object_ref = self._resolve_operand(
                fact.object, binding, artifact_ref, relation_by_fact, fact.id, "object"
            )

            fact_id = deterministic_id("fact", subject_ref, fact.predicate.value, object_ref)

            existing = reader.find_existing_fact(subject_ref, fact.predicate, object_ref)
            if existing is not None:
                target_id = existing.id
            elif fact_id in promoted_in_this_delta:
                target_id = fact_id
            else:
                node = PersistedFact(
                    id=fact_id,
                    subject_ref=subject_ref,
                    predicate=fact.predicate,
                    object_ref=object_ref,
                    fact_type=fact.fact_type.value,
                )
                promoted_in_this_delta[fact_id] = node
                delta.promoted_facts.append(node)
                target_id = fact_id

            delta.evidence_records.append(
                EvidenceRecord(
                    id=deterministic_id("evidence", artifact.id, fact.id),
                    persisted_fact_id=target_id,
                    source_artifact_id=artifact.id,
                    source_fact_id=fact.id,
                    artifact_type=artifact.type.value,
                    recorded_at=artifact.recorded_at,
                    confidence=fact.confidence,
                    authority=authority,
                    supporting_statements=list(fact.supporting_statements),
                )
            )

        return delta

    @staticmethod
    def _resolve_operand(
        text: str,
        binding: BindingResult,
        artifact_ref: str,
        relation_by_fact: dict,
        fact_id: str,
        position: str,
    ) -> str:
        if text.strip().lower() in _SELF_REFERENCES:
            return artifact_ref

        relation = relation_by_fact.get(fact_id)
        if relation is not None:
            local_id = (
                relation.subject_entity_id if position == "subject"
                else relation.object_entity_id
            )
            resolved = binding.local_id_to_global.get(local_id)
            if resolved:
                return resolved

        return binding.entity_bindings.get(text.strip().lower(), text)
