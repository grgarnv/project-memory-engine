"""Compiler stages and golden IR."""
import json
from pathlib import Path

import pytest

from memory_engine.compiler import MemoryCompiler, observe, segment
from memory_engine.ir import ArtifactType
from memory_engine.ontology import EntityType, Predicate
from tests.conftest import GOLDEN, make_artifact

CASES = sorted(p.name for p in GOLDEN.iterdir() if p.is_dir())


@pytest.mark.parametrize("case", CASES)
def test_golden_ir(case):
    case_dir = GOLDEN / case
    expected = json.loads((case_dir / "expected.json").read_text())
    artifact = make_artifact((case_dir / "input.md").read_text(), ArtifactType.PR)

    result = MemoryCompiler().compile(artifact)
    actual = [
        {"subject": s.subject, "predicate": s.predicate, "target": s.target}
        for s in result["statements"]
    ]

    assert actual == expected["statements"]
    if "fact_count" in expected:
        assert len(result["facts"]) == expected["fact_count"]
    if "entities" in expected:
        assert sorted(e.canonical_name for e in result["entities"]) == sorted(expected["entities"])


@pytest.mark.parametrize("case", CASES)
def test_compilation_is_reproducible(case):
    """Same bytes, same config, same IR - the compiler's whole promise."""
    content = (GOLDEN / case / "input.md").read_text()
    first = MemoryCompiler().compile(make_artifact(content)).to_json()
    second = MemoryCompiler().compile(make_artifact(content)).to_json()
    assert first == second


def test_section_headers_set_observation_type():
    artifact = make_artifact(
        "# ADR 1\n\n## Status\nAccepted\n\n## Decision\nUse Redis for caching.\n"
    )
    observations = observe(artifact)
    types = {o.type for o in observations}
    assert "status" in types and "decision" in types


def test_standalone_headers_are_dropped_at_segment():
    artifact = make_artifact("# Title Only\n\nSome body text.\n")
    segments = segment(observe(artifact))
    assert all("Title Only" not in s.text for s in segments)


def test_labelled_paragraph_merges_with_its_body():
    artifact = make_artifact("Do a thing.\n\nReason:\n\nBecause of latency.\n")
    segments = segment(observe(artifact))
    assert any("Because of latency" in s.text for s in segments)


def test_hedged_claim_is_not_promoted(compiler):
    result = compiler.compile(make_artifact("# PR\n\nThis should improve performance.\n"))
    assert result["claims"][0].confidence < 0.7
    assert result["facts"] == []


def test_every_fact_links_back_to_a_claim(compiler):
    result = compiler.compile(make_artifact("Use Redis for caching.\n"))
    claim_ids = {c.id for c in result["claims"]}
    assert result["facts"]
    assert all(f.source_claim in claim_ids for f in result["facts"])


def test_claims_carry_confidence(compiler):
    result = compiler.compile(make_artifact("Use Redis for caching.\n"))
    assert len(result["claims"]) == len(result["statements"])
    assert all(0.0 <= c.confidence <= 1.0 for c in result["claims"])


def test_facts_normalize_onto_the_ontology(compiler):
    result = compiler.compile(make_artifact("Use Redis for caching.\n"))
    assert Predicate.UNKNOWN not in {f.predicate for f in result["facts"]}
