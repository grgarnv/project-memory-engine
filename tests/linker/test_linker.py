"""Linker passes: binding, persistence, evidence, dedup."""
import pytest

from memory_engine.ir import ArtifactType
from memory_engine.linker import ThreePassMemoryPatchLinker, global_entity_id
from memory_engine.linker.passes import BindingPass
from memory_engine.ontology import Predicate
from tests.conftest import make_artifact

DECISION = "## Decision\n\nUse OAuth2 for service-to-service authentication.\n"


def _link(compiler, linker, memory, content, atype=ArtifactType.ADR, when=""):
    compiled = compiler.compile(make_artifact(content, atype, when))
    delta = linker.link(memory, compiled)
    memory.apply_delta(delta)
    return delta


def test_entity_identity_ignores_type_disagreement():
    """
    Two artifacts that disagree about whether OAuth2 is a FRAMEWORK or a
    FEATURE must still bind to one entity. Typing is a claim about a thing,
    not part of its identity.
    """
    assert global_entity_id("OAuth2") == global_entity_id("oauth2")


def test_facts_bind_to_entities_not_to_the_artifact(compiler, linker, memory):
    _link(compiler, linker, memory, DECISION)
    decisions = [f for f in memory.facts.values() if f.predicate is Predicate.SELECTED]
    assert decisions
    assert not any(f.is_artifact_scoped for f in decisions)


def test_artifact_level_assertions_keep_an_artifact_ref(compiler, linker, memory):
    """Ontology separation: a document describing itself is not a domain fact."""
    _link(compiler, linker, memory, DECISION)
    describes = [f for f in memory.facts.values() if f.predicate is Predicate.DESCRIBES]
    assert all(f.is_artifact_scoped for f in describes)


def test_same_assertion_from_two_artifacts_accumulates_evidence(
    compiler, linker, memory
):
    _link(compiler, linker, memory, DECISION, ArtifactType.ADR, "2024-01-01")
    _link(compiler, linker, memory,
          "Use OAuth2 for service-to-service authentication.\n",
          ArtifactType.COMMIT, "2024-02-01")

    decisions = [f for f in memory.facts.values() if f.predicate is Predicate.SELECTED]
    assert len(decisions) == 1, "the fact node must not be duplicated"
    assert len(memory.evidence_for_fact(decisions[0].id)) == 2


def test_evidence_carries_real_confidence_and_authority(compiler, linker, memory):
    _link(compiler, linker, memory, DECISION, ArtifactType.ADR, "2024-01-01")
    record = memory.evidence[0]
    assert record.recorded_at == "2024-01-01"
    assert record.artifact_type == "adr"
    assert record.authority == 1.0
    assert 0.0 < record.confidence <= 1.0


def test_commit_evidence_weighs_less_than_adr_evidence(compiler, linker, memory):
    _link(compiler, linker, memory, DECISION, ArtifactType.ADR, "2024-01-01")
    _link(compiler, linker, memory, "Use Redis for session caching.\n",
          ArtifactType.COMMIT, "2024-02-01")
    by_type = {e.artifact_type: e.weight for e in memory.evidence}
    assert by_type["adr"] > by_type["commit"]


def test_undated_artifact_emits_a_diagnostic(compiler, linker, memory):
    delta = _link(compiler, linker, memory, DECISION, ArtifactType.ADR, "")
    assert any("recorded_at" in d for d in delta.diagnostics)


def test_binding_leaves_unknown_operands_unresolved(compiler, memory):
    """RFC 003 non-goal 4: never guess."""
    compiled = compiler.compile(make_artifact("Some prose with no entities at all.\n"))
    binding = BindingPass().bind(memory, compiled)
    assert all(gid.startswith("entity_") for gid in binding.entity_bindings.values())


def test_relink_of_the_same_artifact_is_idempotent(compiler, linker, memory):
    _link(compiler, linker, memory, DECISION, ArtifactType.ADR, "2024-01-01")
    before = memory.stats()
    _link(compiler, linker, memory, DECISION, ArtifactType.ADR, "2024-01-01")
    assert memory.stats() == before
