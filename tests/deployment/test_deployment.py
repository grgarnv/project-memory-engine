"""
Deployment path: sources, corrections, scale, pilot measurement, MCP.

Everything here is about running against a real project rather than a fixture.
"""
import json
import subprocess

import pytest

from memory_engine.correction import Correction, CorrectionError, apply_correction, retract
from memory_engine.ingest import Ingestor
from memory_engine.ir import ArtifactType
from memory_engine.memory.model import GlobalEntityBinding, MemoryDelta, PersistedFact
from memory_engine.ontology import EntityType, Predicate
from memory_engine.pilot import run_pilot
from memory_engine.resolve import BeliefResolver
from memory_engine.sources import FilesystemSource, GitSource, GitHubSource
from memory_engine.store import InMemoryProjectMemory, SQLiteProjectMemory
from tests.conftest import FIXTURES, REPO_ROOT

QUEUE = FIXTURES / "eval" / "queue-consolidation"


@pytest.fixture
def memory():
    store = InMemoryProjectMemory()
    Ingestor(memory=store).ingest_scenario(QUEUE)
    return store


# -- sources ----------------------------------------------------------------

def test_filesystem_source_reads_a_directory():
    artifacts = list(FilesystemSource(REPO_ROOT / "docs" / "rfcs").fetch())
    assert artifacts
    assert all(a.content for a in artifacts)


def test_git_source_yields_commits_oldest_first():
    artifacts = list(GitSource(REPO_ROOT, max_commits=5).fetch())
    if not artifacts:
        pytest.skip("not a git repository")
    dates = [a.recorded_at for a in artifacts]
    assert dates == sorted(dates)


def test_git_source_skips_merge_noise():
    source = GitSource(REPO_ROOT)
    assert source._is_noise("Merge branch 'main' into feature")
    assert source._is_noise("bump lodash from 1 to 2")
    assert not source._is_noise("Use OAuth2 for service-to-service authentication")


def test_git_watermark_is_a_sha_not_a_date():
    """Commit dates are not monotonic across merges; SHAs are a real cursor."""
    artifacts = list(GitSource(REPO_ROOT, max_commits=3).fetch())
    if not artifacts:
        pytest.skip("not a git repository")
    assert len(GitSource(REPO_ROOT).watermark_for(artifacts[-1])) == 40


def test_second_ingestion_run_does_no_work(tmp_path):
    """The whole point of a watermark."""
    store = SQLiteProjectMemory(tmp_path / "inc.db")
    ingestor = Ingestor(memory=store)
    first = ingestor.ingest_source(FilesystemSource(REPO_ROOT / "docs" / "rfcs"))
    second = ingestor.ingest_source(FilesystemSource(REPO_ROOT / "docs" / "rfcs"))
    assert first.produced > 0
    assert second.produced == 0
    store.close()


def test_github_source_needs_no_network_to_test():
    """Transport is injectable, so the adapter is testable without credentials."""
    pages = [[{
        "number": 7, "title": "Adopt Kafka", "body": "Use Kafka for messaging.",
        "created_at": "2024-01-02T00:00:00Z", "updated_at": "2024-01-03T00:00:00Z",
        "html_url": "https://example.invalid/7",
    }], []]

    def fake_open(url):
        if "comments" in url:
            return [{"user": {"login": "dev"}, "body": "Agreed, RabbitMQ is out."}]
        return pages.pop(0) if pages else []

    artifacts = list(GitHubSource("o", "r", opener=fake_open).fetch())
    assert len(artifacts) == 1
    assert "Agreed, RabbitMQ is out." in artifacts[0].content, "review comments carry the reasoning"
    assert artifacts[0].type is ArtifactType.PR


def test_github_token_is_never_an_argument():
    """A token passed as a parameter ends up in logs and stack traces."""
    import inspect
    assert "token" not in inspect.signature(GitHubSource.__init__).parameters


# -- correction loop --------------------------------------------------------

def test_correction_retires_a_fact(memory):
    belief = BeliefResolver(memory).explain("asynchronous messaging")
    fact_id = belief.decision.fact_id
    apply_correction(memory, Correction(fact_id, "arnav", "never actually adopted"))
    assert memory.is_superseded(fact_id)


def test_correction_deletes_nothing(memory):
    """Append-only holds even when a human says the fact is wrong."""
    fact_id = BeliefResolver(memory).explain("asynchronous messaging").decision.fact_id
    before = len(memory.facts)
    apply_correction(memory, Correction(fact_id, "arnav", "wrong"))
    assert memory.get_fact(fact_id) is not None
    assert len(memory.facts) > before, "the correction itself is recorded, not applied silently"


def test_correction_names_its_author_and_reason(memory):
    fact_id = BeliefResolver(memory).explain("asynchronous messaging").decision.fact_id
    apply_correction(memory, Correction(fact_id, "arnav", "never actually adopted"))
    edge = next(e for e in memory.supersessions if e.superseded_fact_id == fact_id)
    assert "arnav" in edge.reason
    assert edge.basis == "human_correction"
    assert edge.source_artifact_id


def test_correction_outranks_document_evidence(memory):
    from memory_engine.ir import ARTIFACT_AUTHORITY
    assert ARTIFACT_AUTHORITY[ArtifactType.CORRECTION] > ARTIFACT_AUTHORITY[ArtifactType.ADR]


def test_correcting_an_unknown_fact_is_refused(memory):
    with pytest.raises(CorrectionError):
        retract(memory, Correction("fact_nonexistent", "arnav", "nope"))


def test_correcting_an_already_retired_fact_is_refused(memory):
    fact_id = BeliefResolver(memory).explain("asynchronous messaging").decision.fact_id
    apply_correction(memory, Correction(fact_id, "arnav", "wrong"))
    with pytest.raises(CorrectionError):
        retract(memory, Correction(fact_id, "someone", "also wrong"))


# -- scale ------------------------------------------------------------------

def test_queries_stay_fast_at_scale(tmp_path):
    """
    Linear scans are fine at 300 facts and fatal at 300,000. This is a
    correctness test disguised as a performance one: if facts_mentioning
    regresses to a full scan, this takes minutes instead of milliseconds.
    """
    import time

    store = SQLiteProjectMemory(tmp_path / "scale.db")
    n = 20000
    delta = MemoryDelta(artifact_id="bulk", artifact_recorded_at="2024-01-01")
    for i in range(n):
        eid = f"entity_{i:06d}"
        delta.bound_entities.append(
            GlobalEntityBinding(f"component {i}", eid, EntityType.COMPONENT, []))
        delta.promoted_facts.append(
            PersistedFact(f"fact_{i:06d}", eid, Predicate.USES, f"entity_{(i * 7) % n:06d}"))
    store.apply_delta(delta)

    start = time.time()
    for i in range(100):
        store.facts_mentioning(f"entity_{i * 37 % n:06d}")
    elapsed = time.time() - start
    assert elapsed < 1.0, f"100 lookups over {n} facts took {elapsed:.1f}s"
    store.close()


def test_identity_closure_is_one_query(tmp_path):
    store = SQLiteProjectMemory(tmp_path / "closure.db")
    store.apply_delta(MemoryDelta(
        artifact_id="a",
        bound_entities=[
            GlobalEntityBinding("gateway", "entity_a", EntityType.COMPONENT, []),
            GlobalEntityBinding("edge service", "entity_b", EntityType.COMPONENT, []),
            GlobalEntityBinding("APIGW", "entity_c", EntityType.COMPONENT, []),
        ],
        promoted_facts=[
            PersistedFact("f1", "entity_a", Predicate.SAME_AS, "entity_b"),
            PersistedFact("f2", "entity_b", Predicate.SAME_AS, "entity_c"),
        ],
    ))
    assert set(store.identity_closure("entity_a")) == {"entity_a", "entity_b", "entity_c"}
    store.close()


def test_closure_is_bounded(tmp_path):
    store = SQLiteProjectMemory(tmp_path / "bounded.db")
    assert len(store.identity_closure("entity_x", max_size=5)) <= 5
    store.close()


# -- pilot measurement ------------------------------------------------------

def test_pilot_scores_correct_answers(memory):
    report = run_pilot(memory, FIXTURES / "pilot" / "questions.json")
    assert report.total == 3
    assert report.correct >= 1


def test_answering_a_question_with_no_recorded_position_is_wrong(memory, tmp_path):
    """
    The metric must not reward confidence. If memory has no position and the
    engine produces one, that is the expensive failure.
    """
    spec = tmp_path / "q.json"
    spec.write_text(json.dumps({"questions": [
        {"ask": "asynchronous messaging", "expect": None},
    ]}))
    report = run_pilot(memory, spec)
    assert report.wrong == 1
    assert "confidently wrong" in report.render()


def test_declining_is_not_counted_as_wrong(memory, tmp_path):
    spec = tmp_path / "q.json"
    spec.write_text(json.dumps({"questions": [{"ask": "quantum tunnelling", "expect": None}]}))
    report = run_pilot(memory, spec)
    assert report.wrong == 0
    assert report.correct == 1


# -- MCP --------------------------------------------------------------------

def test_mcp_lists_its_tools(tmp_path):
    from memory_engine.mcp_server import MemoryMCPServer
    server = MemoryMCPServer(str(tmp_path / "mcp.db"))
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in response["result"]["tools"]}
    assert {"ask_project", "project_timeline", "check_constraint", "correct_fact"} <= names


def test_mcp_answers_from_memory(tmp_path):
    from memory_engine.mcp_server import MemoryMCPServer
    db = tmp_path / "mcp.db"
    store = SQLiteProjectMemory(db)
    Ingestor(memory=store).ingest_scenario(QUEUE)
    store.close()

    server = MemoryMCPServer(str(db))
    text = server.call("ask_project", {"entity": "asynchronous messaging"})
    assert "Kafka" in text


def test_mcp_exposes_no_deletion_tool(tmp_path):
    """The only write path is a correction, which is append-only."""
    from memory_engine.mcp_server import TOOLS
    names = {t["name"] for t in TOOLS}
    assert not any("delete" in n or "remove" in n or "drop" in n for n in names)


def test_mcp_rejects_unknown_methods(tmp_path):
    from memory_engine.mcp_server import MemoryMCPServer
    server = MemoryMCPServer(str(tmp_path / "mcp.db"))
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "nope"})
    assert response["error"]["code"] == -32601


# -- LLM extraction reproducibility -----------------------------------------

def test_cached_extraction_calls_the_model_once():
    """
    RFC 004 §3: an LLM extractor is only reproducible if it is pinned and
    cached. Two identical compilations must not produce two model calls.
    """
    from memory_engine.compiler.extractors.llm import (
        CachedLLMStatementExtractor, ExtractionCache, MockLLMProvider,
    )
    from memory_engine.ir import Segment, SegmentKind

    calls = []

    class Counting(MockLLMProvider):
        def generate(self, prompt):
            calls.append(prompt)
            return super().generate(prompt)

    extractor = CachedLLMStatementExtractor(
        provider=Counting(canned_response=json.dumps(
            [{"subject": "API Gateway", "predicate": "uses", "target": "OAuth2"}])),
        cache=ExtractionCache(":memory:"), model="test-model",
    )
    segment = Segment(kind=SegmentKind.DESCRIPTION, text="The API Gateway uses OAuth2.")
    first = extractor.extract(segment)
    second = extractor.extract(segment)

    assert len(calls) == 1
    assert [(s.subject, s.target) for s in first] == [(s.subject, s.target) for s in second]


def test_changing_the_model_changes_the_cache_key():
    """A model upgrade is a new compilation, not a correction of the old one."""
    from memory_engine.compiler.extractors.llm import ExtractionCache
    a = ExtractionCache.key("text", "model-a", "1", 0.0, "P")
    b = ExtractionCache.key("text", "model-b", "1", 0.0, "P")
    c = ExtractionCache.key("text", "model-a", "2", 0.0, "P")
    assert len({a, b, c}) == 3


def test_compilation_records_which_extractor_produced_it():
    from memory_engine.compiler import MemoryCompiler
    from tests.conftest import make_artifact
    result = MemoryCompiler().compile(make_artifact("The gateway uses OAuth2.\n"))
    assert "extractor" in result.metadata
