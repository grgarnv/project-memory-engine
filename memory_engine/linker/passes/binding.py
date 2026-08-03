"""
Pass 1: Binding.

Binds artifact-local entity mentions to persistent global entity IDs and
resolves the artifact's self-reference. Zero semantic reasoning: an entity that
does not match anything known gets a fresh deterministic ID from its name, and
an operand that matches nothing stays unresolved rather than being guessed.

Global entity IDs hash the canonical NAME only, never the entity type. Two
artifacts that disagree about whether OAuth2 is a FRAMEWORK or a FEATURE must
still land on the same entity - typing is a claim about a thing, not part of
its identity.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memory_engine.ir import CompiledArtifact, deterministic_id
from memory_engine.memory.contracts import MemoryReader
from memory_engine.memory.model import ArtifactRef, GlobalEntityBinding


def global_entity_id(canonical_name: str) -> str:
    return deterministic_id("entity", canonical_name.strip().lower())


@dataclass(slots=True)
class BindingResult:
    """Everything Pass 2 needs from Pass 1."""
    entity_bindings: dict[str, str] = field(default_factory=dict)  # lowered name -> global id
    local_id_to_global: dict[str, str] = field(default_factory=dict)  # compiler Entity.id -> global id
    bound_list: list[GlobalEntityBinding] = field(default_factory=list)
    artifact_ref: ArtifactRef | None = None
    diagnostics: list[str] = field(default_factory=list)


class BindingPass:
    def bind(self, reader: MemoryReader, compiled: CompiledArtifact) -> BindingResult:
        result = BindingResult(artifact_ref=ArtifactRef(compiled.artifact.id))

        for entity in compiled.entities:
            key = entity.canonical_name.strip().lower()
            existing = reader.find_entity_by_canonical_name(entity.canonical_name)
            gid = existing or global_entity_id(entity.canonical_name)

            result.entity_bindings[key] = gid
            result.local_id_to_global[entity.id] = gid
            for alias in entity.aliases:
                result.entity_bindings.setdefault(alias.strip().lower(), gid)

            result.bound_list.append(
                GlobalEntityBinding(
                    local_canonical_name=entity.canonical_name,
                    global_entity_id=gid,
                    entity_type=entity.entity_type,
                    aliases=list(entity.aliases),
                )
            )

        return result
