"""
Entity recognition.

Three recognizers, composed by default:

    GeneralEntityRecognizer  known software vocabulary + CamelCase identifiers
    PhraseEntityRecognizer   the operands of relational patterns
    CompositeEntityRecognizer  merges them and suppresses subsumed names

PhraseEntityRecognizer exists to close a specific gap: if a phrase can appear
as a fact operand, it must also exist as an entity, or the linker binds a fact
to a raw string and the concept never enters the graph. Both read the same
pattern table, so they cannot drift apart.
"""
from __future__ import annotations

import re

from memory_engine.compiler.extractors.base import EntityRecognizer
from memory_engine.compiler.extractors.patterns import find_relational_matches
from memory_engine.ir import Entity
from memory_engine.ontology import EntityType

# Head nouns that indicate what kind of thing a phrase is. Checked longest-first
# so "authentication mechanism" beats "authentication".
_TYPE_HINTS: tuple[tuple[str, EntityType], ...] = (
    ("authentication", EntityType.CAPABILITY),
    ("authorization", EntityType.CAPABILITY),
    ("validation", EntityType.CAPABILITY),
    ("caching", EntityType.CAPABILITY),
    ("logging", EntityType.CAPABILITY),
    ("gateway", EntityType.COMPONENT),
    ("service", EntityType.SERVICE),
    ("api", EntityType.API),
    ("database", EntityType.DATABASE),
    ("module", EntityType.MODULE),
    ("library", EntityType.LIBRARY),
    ("pipeline", EntityType.COMPONENT),
    ("queue", EntityType.COMPONENT),
)


def _infer_type(name: str) -> EntityType:
    lowered = name.lower()
    for hint, etype in _TYPE_HINTS:
        if hint in lowered:
            return etype
    return EntityType.UNKNOWN


class GeneralEntityRecognizer(EntityRecognizer):
    """Known software vocabulary plus a CamelCase identifier heuristic."""

    _KNOWN_PATTERNS: tuple[tuple[str, EntityType], ...] = (
        (r"\bAPI Gateway\b", EntityType.COMPONENT),
        (r"\bJWT validation\b", EntityType.FEATURE),
        (r"\bauthentication\b", EntityType.FEATURE),
        (r"\b(PostgreSQL|Postgres|Redis|MongoDB|MySQL|SQLite|DynamoDB|Elasticsearch)\b",
         EntityType.DATABASE),
        (r"\b(Kubernetes|K8s|Docker|Terraform|Helm|Ansible)\b", EntityType.UNKNOWN),
        (r"\b(React|Vue|Angular|Next\.js|Node\.js|Django|FastAPI|Flask|Spring Boot)\b",
         EntityType.FRAMEWORK),
        (r"\b(Kafka|RabbitMQ|NATS|Pulsar|AWS SQS)\b", EntityType.UNKNOWN),
        (r"\b(OAuth2|OAuth|JWT|gRPC|GraphQL|REST|SAML)\b", EntityType.FEATURE),
    )

    def recognize(self, text: str) -> list[Entity]:
        entities: dict[str, Entity] = {}

        for pattern, entity_type in self._KNOWN_PATTERNS:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                key = match.lower()
                if key not in entities:
                    entities[key] = Entity(
                        canonical_name=match,
                        entity_type=entity_type,
                        aliases=[match],
                    )

        for ident in re.findall(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b", text):
            key = ident.lower()
            if key not in entities:
                entities[key] = Entity(
                    canonical_name=ident,
                    entity_type=EntityType.UNKNOWN,
                    aliases=[ident],
                )

        return list(entities.values())


class PhraseEntityRecognizer(EntityRecognizer):
    """Registers relational-pattern operands as entities."""

    def recognize(self, text: str) -> list[Entity]:
        entities: dict[str, Entity] = {}
        for match in find_relational_matches(text):
            for name in (match.subject, match.object):
                key = name.lower()
                if key not in entities:
                    entities[key] = Entity(
                        canonical_name=name,
                        entity_type=_infer_type(name),
                        aliases=[name],
                    )
        return list(entities.values())


class CompositeEntityRecognizer(EntityRecognizer):
    """
    Merges recognizers and drops names strictly contained in a longer one from
    the same text ("authentication" inside "service-to-service authentication").

    Subsumption is suppressed, not merged: the shorter name is dropped for this
    artifact rather than aliased to the longer one, because deciding that two
    names denote the same concept is a linking judgement, not a compiler one.
    """

    def __init__(self, recognizers: list[EntityRecognizer]):
        self.recognizers = recognizers

    def recognize(self, text: str) -> list[Entity]:
        merged: dict[str, Entity] = {}
        for recognizer in self.recognizers:
            for entity in recognizer.recognize(text):
                key = entity.canonical_name.lower()
                existing = merged.get(key)
                if existing is None:
                    merged[key] = entity
                elif existing.entity_type is EntityType.UNKNOWN:
                    merged[key] = entity

        names = list(merged)
        keep = {}
        for key, entity in merged.items():
            subsumed = any(
                other != key and re.search(rf"\b{re.escape(key)}\b", other)
                for other in names
            )
            if not subsumed:
                keep[key] = entity
        return list(keep.values())


def default_entity_recognizer() -> EntityRecognizer:
    return CompositeEntityRecognizer(
        [GeneralEntityRecognizer(), PhraseEntityRecognizer()]
    )
