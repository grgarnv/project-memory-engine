"""
Entity resolution and Relation construction.

A Fact carries text operands. A Relation carries entity IDs. The resolver maps
one to the other by exact canonical-name and alias matching; ambiguous or
unknown operands are left unresolved rather than guessed.

Relations matter to the linker, not just to the compiler: when a Relation exists
for a Fact, the linker binds that fact through resolved entities instead of
string lookup. See memory_engine/linker/passes/persistence.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from memory_engine.compiler.extractors.base import EntityResolver, RelationExtractor
from memory_engine.ir import Claim, Entity, Fact, Relation


@dataclass(slots=True)
class ResolvedFact:
    """Compiler-internal: a Fact plus whatever its operands resolved to."""
    fact: Fact
    subject_entity: Entity | None = None
    object_entity: Entity | None = None
    confidence: float = 1.0


class DeterministicEntityResolver(EntityResolver):
    """Exact canonical-name and alias matching, case-insensitive."""

    def resolve(
        self,
        facts: list[Fact],
        entities: list[Entity],
        claims: list[Claim] | None = None,
    ) -> list[ResolvedFact]:
        lookup: dict[str, list[Entity]] = {}
        for entity in entities:
            keys = {entity.canonical_name.lower()}
            keys.update(alias.lower() for alias in entity.aliases)
            for key in keys:
                bucket = lookup.setdefault(key, [])
                if entity not in bucket:
                    bucket.append(entity)

        def resolve_one(text: str) -> Entity | None:
            matches = lookup.get(text.lower(), [])
            return matches[0] if len(matches) == 1 else None

        claim_map = {c.id: c for c in (claims or [])}

        resolved: list[ResolvedFact] = []
        for fact in facts:
            confidence = fact.confidence
            if fact.source_claim in claim_map:
                confidence = claim_map[fact.source_claim].confidence
            resolved.append(
                ResolvedFact(
                    fact=fact,
                    subject_entity=resolve_one(fact.subject),
                    object_entity=resolve_one(fact.object),
                    confidence=confidence,
                )
            )
        return resolved


class RuleBasedRelationExtractor(RelationExtractor):
    """Builds a Relation for every fact whose operands both resolved."""

    def extract(self, resolved_facts: list[ResolvedFact]) -> list[Relation]:
        return [
            Relation(
                subject_entity_id=rf.subject_entity.id,
                predicate=rf.fact.predicate,
                object_entity_id=rf.object_entity.id,
                source_fact_id=rf.fact.id,
                confidence=rf.confidence,
            )
            for rf in resolved_facts
            if rf.subject_entity and rf.object_entity
        ]
