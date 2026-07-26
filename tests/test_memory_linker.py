import pytest
from memory_engine.ir import Artifact, ArtifactType
from memory_engine.ontology import EntityType, Predicate
from memory_engine.pipeline import MemoryCompiler
from memory_engine.patch import (
    ArtifactRef,
    GlobalEntityBinding,
    EvidenceRecord,
    PersistedFact,
    SupersessionEdge,
    ConflictEdge,
    MemoryDelta,
    ThreePassMemoryPatchLinker,
    InMemoryProjectMemory,
    ExplicitDeprecationRule,
    SingleOccupancyDecisionRule,
    DirectNegationConflictRule,
    AnalysisPipeline,
    AnalysisRule,
)


def test_linker_single_artifact_execution():
    compiler = MemoryCompiler()
    linker = ThreePassMemoryPatchLinker()
    memory = InMemoryProjectMemory()

    artifact = Artifact(type=ArtifactType.PR, content="Reason: Move JWT validation into API Gateway.")
    compiled = compiler.compile(artifact)

    delta = linker.link(memory, compiled)

    assert delta.artifact_id == artifact.id
    assert len(delta.bound_entities) > 0
    assert len(delta.evidence_records) > 0

    memory.apply_delta(delta)

    assert len(memory.facts) > 0
    assert len(memory.evidence) == len(delta.evidence_records)


def test_linker_idempotency_repeated_runs():
    compiler = MemoryCompiler()
    linker = ThreePassMemoryPatchLinker()
    memory = InMemoryProjectMemory()

    artifact = Artifact(type=ArtifactType.PR, content="Reason: Move JWT validation into API Gateway.")
    compiled = compiler.compile(artifact)

    # First run
    delta1 = linker.link(memory, compiled)
    memory.apply_delta(delta1)

    initial_fact_count = len(memory.facts)
    initial_evidence_count = len(memory.evidence)

    # Second run (exact same compiled artifact)
    delta2 = linker.link(memory, compiled)

    # Delta2 should produce 0 new promoted facts (deduplicated)
    assert len(delta2.promoted_facts) == 0

    memory.apply_delta(delta2)

    # Memory state fact count must remain identical
    assert len(memory.facts) == initial_fact_count


def test_evidence_accumulation_across_multiple_artifacts():
    compiler = MemoryCompiler()
    linker = ThreePassMemoryPatchLinker()
    memory = InMemoryProjectMemory()

    # Construct two compiled artifacts that both assert (API Gateway --uses--> JWT validation)
    from memory_engine.ir import Fact
    art1 = Artifact(type=ArtifactType.ADR, content="API Gateway uses JWT validation.")
    comp1 = compiler.compile(art1)
    comp1.facts = [Fact(subject="API Gateway", predicate=Predicate.USES, object="JWT validation")]
    delta1 = linker.link(memory, comp1)
    memory.apply_delta(delta1)

    initial_fact_count = len(memory.facts)
    initial_evidence_count = len(memory.evidence)
    assert initial_fact_count == 1
    assert initial_evidence_count == 1

    # Artifact 2 asserting the exact same domain relation
    art2 = Artifact(type=ArtifactType.COMMIT, content="API Gateway uses JWT validation.")
    comp2 = compiler.compile(art2)
    comp2.facts = [Fact(subject="API Gateway", predicate=Predicate.USES, object="JWT validation")]
    delta2 = linker.link(memory, comp2)
    memory.apply_delta(delta2)

    # Fact count should remain constant (deduplicated: 1), but Evidence count should accumulate to 2!
    assert len(memory.facts) == initial_fact_count
    assert len(memory.evidence) == initial_evidence_count + 1



def test_artifact_ref_symbol_resolution():
    compiler = MemoryCompiler()
    linker = ThreePassMemoryPatchLinker()
    memory = InMemoryProjectMemory()

    artifact = Artifact(type=ArtifactType.PR, content="Reason: Fix auth bug")
    compiled = compiler.compile(artifact)

    delta = linker.link(memory, compiled)

    # Verify CURRENT_CHANGE resolved to artifact:id reference rather than a domain Entity
    subject_refs = {f.subject_ref for f in delta.promoted_facts}
    assert f"artifact:{artifact.id}" in subject_refs

    # Ensure no Entity("Current Change") was bound
    bound_names = [b.local_canonical_name.lower() for b in delta.bound_entities]
    assert "current change" not in bound_names


def test_conservative_single_occupancy_decision_rule():
    compiler = MemoryCompiler()
    linker = ThreePassMemoryPatchLinker()
    memory = InMemoryProjectMemory()

    from memory_engine.ir import Fact
    # Artifact 1 selects JWT for Authentication
    art1 = Artifact(type=ArtifactType.ADR, content="Authentication selects JWT validation")
    comp1 = compiler.compile(art1)
    comp1.facts.append(Fact(subject="Authentication", predicate=Predicate.SELECTED, object="JWT validation"))
    delta1 = linker.link(memory, comp1)
    memory.apply_delta(delta1)

    # Artifact 2 selects OAuth for Authentication
    art2 = Artifact(type=ArtifactType.ADR, content="Authentication selects OAuth")
    comp2 = compiler.compile(art2)
    comp2.facts.append(Fact(subject="Authentication", predicate=Predicate.SELECTED, object="OAuth"))
    delta2 = linker.link(memory, comp2)

    # Verify SingleOccupancyDecisionRule generated a SupersessionEdge
    assert len(delta2.supersessions) > 0
    s_edge = delta2.supersessions[0]
    assert "Single-occupancy" in s_edge.reason

    memory.apply_delta(delta2)

    # Verify original JWT decision is superseded while preserved in history
    assert s_edge.superseded_fact_id in memory.superseded_fact_ids



def test_custom_analysis_rule_plugin():
    class CustomRule(AnalysisRule):
        def analyze(self, reader: InMemoryProjectMemory, delta: MemoryDelta) -> None:
            delta.diagnostics.append("CustomRuleExecuted")

    pipeline = AnalysisPipeline(rules=[CustomRule()])
    linker = ThreePassMemoryPatchLinker(analysis_pipeline=pipeline)
    memory = InMemoryProjectMemory()

    artifact = Artifact(type=ArtifactType.PR, content="Reason: Test custom rule")
    compiled = MemoryCompiler().compile(artifact)

    delta = linker.link(memory, compiled)
    assert "CustomRuleExecuted" in delta.diagnostics
