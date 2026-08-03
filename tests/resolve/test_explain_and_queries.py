"""Explanation and query surfaces."""
import pytest

from memory_engine.ingest import Ingestor
from memory_engine.resolve import BeliefResolver, ProjectQueries, explain
from memory_engine.store import InMemoryProjectMemory
from tests.conftest import SCENARIOS

AUTH = "service-to-service authentication"


@pytest.fixture
def memory():
    store = InMemoryProjectMemory()
    Ingestor(memory=store).ingest_scenario(SCENARIOS / "oauth2-supersedes-jwt")
    return store


def test_explanation_states_the_current_position(memory):
    text = explain(BeliefResolver(memory).explain(AUTH))
    assert "OAuth2" in text
    assert text.startswith("The project uses")


def test_explanation_names_what_was_replaced(memory):
    """The half of the answer document retrieval never gives."""
    text = explain(BeliefResolver(memory).explain(AUTH))
    assert "replaced an earlier position" in text
    assert "JWT" in text


def test_explanation_describes_evidence_without_overstating(memory):
    text = explain(BeliefResolver(memory).explain(AUTH))
    assert "corroborated by" in text  # three artifacts, not one
    assert "2024" in text


def test_explanation_of_an_unknown_entity_admits_it(memory):
    text = explain(BeliefResolver(memory).explain("Kerberos"))
    assert "no recorded position" in text


def test_explanation_surfaces_ordering_caveats():
    """A belief resting on ingestion order must not read as confident."""
    from memory_engine.ir import ArtifactType
    from tests.conftest import make_artifact

    store = InMemoryProjectMemory()
    ingestor = Ingestor(memory=store)
    for content in ("## Decision\n\nUse JWT for service-to-service authentication.\n",
                    "## Decision\n\nUse OAuth2 for service-to-service authentication.\n"):
        ingestor.ingest(make_artifact(content, ArtifactType.ADR, ""))

    text = explain(BeliefResolver(store).explain(AUTH))
    assert "ingestion order" in text


def test_timeline_is_chronological(memory):
    entries = ProjectQueries(memory).timeline(AUTH)
    dated = [e.when for e in entries if e.is_dated]
    assert dated == sorted(dated)


def test_timeline_records_retirement_as_well_as_assertion(memory):
    events = {e.event for e in ProjectQueries(memory).timeline(AUTH)}
    assert events == {"asserted", "retired"}


def test_undated_entries_sort_last_not_first():
    """An unknown date is not the beginning of time."""
    from memory_engine.ir import ArtifactType
    from tests.conftest import make_artifact

    store = InMemoryProjectMemory()
    ingestor = Ingestor(memory=store)
    ingestor.ingest(make_artifact("The API Gateway uses OAuth2.\n", ArtifactType.ADR, ""))
    ingestor.ingest(make_artifact("The API Gateway uses Redis.\n", ArtifactType.ADR, "2024-01-01"))

    entries = ProjectQueries(store).timeline("API Gateway")
    assert entries[0].is_dated
    assert not entries[-1].is_dated


def test_dependents_reports_what_relies_on_a_concept(memory):
    labels = {d.label for d in ProjectQueries(memory).dependents("OAuth2")}
    assert "API Gateway" in labels


def test_dependents_excludes_superseded_relationships(memory):
    """Blast radius must not include what a superseded decision once relied on."""
    assert ProjectQueries(memory).dependents("JWT") == []


def test_health_flags_single_source_beliefs(memory):
    report = ProjectQueries(memory).health(list(memory.facts.values()))
    assert report.total_facts > 0
    assert report.single_source_facts >= 1
    assert any("supporting artifact" in n for n in report.notes)


def test_queries_never_mutate_memory(memory):
    before = memory.stats()
    q = ProjectQueries(memory)
    q.timeline(AUTH); q.dependents("OAuth2"); q.health(list(memory.facts.values()))
    assert memory.stats() == before
