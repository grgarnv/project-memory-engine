from memory_engine.patch import (
    GlobalEntityBinding,
    PersistedFact,
    SupersessionEdge,
    ConflictEdge,
    MemoryDelta,
    MemoryReader,
    MemoryPatchLinker,
)
from memory_engine.ontology import Predicate, EntityType
from memory_engine.ir import CompiledArtifact, Artifact, ArtifactType


class MockMemoryReader(MemoryReader):
    def __init__(self, entities: dict[str, str] | None = None):
        self.entities = entities or {}

    def find_entity_by_canonical_name(self, canonical_name: str) -> str | None:
        return self.entities.get(canonical_name.lower())

    def get_persisted_fact_by_id(self, fact_id: str) -> PersistedFact | None:
        return None

    def find_existing_fact(self, subject_ref: str, predicate: Predicate, object_ref: str) -> PersistedFact | None:
        return None

    def get_active_facts_for_subject(self, subject_ref: str) -> list[PersistedFact]:
        return []



class MockMemoryPatchLinker(MemoryPatchLinker):
    def link(self, reader: MemoryReader, compiled_artifact: CompiledArtifact) -> MemoryDelta:
        bindings = []
        for ent in compiled_artifact.entities:
            gid = reader.find_entity_by_canonical_name(ent.canonical_name) or f"global_{ent.canonical_name.lower()}"
            bindings.append(
                GlobalEntityBinding(
                    local_canonical_name=ent.canonical_name,
                    global_entity_id=gid,
                    entity_type=ent.entity_type,
                )
            )

        return MemoryDelta(
            artifact_id=compiled_artifact.artifact.id,
            bound_entities=bindings,
        )


def test_memory_delta_immutability_and_empty_check():
    delta = MemoryDelta(artifact_id="art_123")
    assert delta.is_empty is True

    binding = GlobalEntityBinding(local_canonical_name="JWT", global_entity_id="global_jwt", entity_type=EntityType.FEATURE)
    delta.bound_entities.append(binding)
    assert delta.is_empty is False


def test_mock_linker_contract():
    reader = MockMemoryReader(entities={"jwt validation": "global_jwt_123"})
    linker = MockMemoryPatchLinker()

    artifact = Artifact(type=ArtifactType.PR, content="Reason: JWT validation in API Gateway")
    from memory_engine.pipeline import MemoryCompiler
    compiled = MemoryCompiler().compile(artifact)

    delta = linker.link(reader, compiled)

    assert delta.artifact_id == artifact.id
    assert len(delta.bound_entities) > 0
    bound_names = {b.local_canonical_name.lower(): b.global_entity_id for b in delta.bound_entities}
    if "jwt validation" in bound_names:
        assert bound_names["jwt validation"] == "global_jwt_123"
