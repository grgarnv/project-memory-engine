"""Compliance, onboarding, and ontology migration."""
import pytest

from memory_engine.apps import ComplianceEngine, brief
from memory_engine.ingest import Ingestor
from memory_engine.ontology import OntologyVersion, Predicate
from memory_engine.ontology_migration import (
    MigrationImpact,
    OntologyMigrator,
    PredicateMigration,
)
from memory_engine.store import InMemoryProjectMemory
from tests.conftest import REPO_ROOT

QUEUE = REPO_ROOT / "fixtures" / "eval" / "queue-consolidation"


@pytest.fixture
def memory():
    store = InMemoryProjectMemory()
    Ingestor(memory=store).ingest_scenario(QUEUE)
    return store


# -- compliance -------------------------------------------------------------

def test_violation_is_detected_against_a_recorded_constraint(memory):
    report = ComplianceEngine(memory).check(
        [("order service", Predicate.USES, "RabbitMQ")]
    )
    assert not report.is_compliant
    assert report.violations[0].object == "RabbitMQ"


def test_violation_cites_the_artifact_that_established_the_rule(memory):
    """A compliance report that cannot cite its authority is an opinion."""
    violation = ComplianceEngine(memory).check(
        [("order service", Predicate.USES, "RabbitMQ")]
    ).violations[0]
    assert violation.established_by
    assert violation.established_at
    assert "forbidden by a constraint established in" in violation.describe()


def test_permitted_relationship_is_not_a_violation(memory):
    report = ComplianceEngine(memory).check([("order service", Predicate.USES, "Kafka")])
    assert report.is_compliant


def test_absence_of_a_rule_is_unknown_not_permission(memory):
    """Memory's silence is not consent."""
    report = ComplianceEngine(memory).check([("billing", Predicate.USES, "Kafka")])
    assert report.is_compliant
    assert report.unknown
    assert "not permission" in report.summary()


def test_superseded_constraints_are_not_enforced():
    """A retired rule is not a rule."""
    store = InMemoryProjectMemory()
    Ingestor(memory=store).ingest_scenario(QUEUE)
    engine = ComplianceEngine(store)

    constraint = engine.constraints_for("order service")[0]
    store.superseded_fact_ids.add(constraint.id)

    assert engine.constraints_for("order service") == []


def test_compliance_checks_across_an_identity_class():
    """A rule about one name binds every name asserted to be the same thing."""
    from memory_engine.ir import ArtifactType
    from tests.conftest import make_artifact

    store = InMemoryProjectMemory()
    ingestor = Ingestor(memory=store)
    ingestor.ingest(make_artifact(
        "The order service must not use RabbitMQ.\n", ArtifactType.ADR, "2024-01-01"))
    ingestor.ingest(make_artifact(
        "RabbitMQ is also known as the legacy broker.\n",
        ArtifactType.DOCUMENT, "2024-02-01"))

    report = ComplianceEngine(store).check(
        [("order service", Predicate.USES, "legacy broker")]
    )
    assert not report.is_compliant


# -- onboarding -------------------------------------------------------------

def test_brief_lists_current_decisions(memory):
    result = brief(memory, list(memory.facts.values()))
    assert any(obj == "Kafka" for _, obj, _ in result.decisions)


def test_brief_separates_what_changed_from_what_is_current(memory):
    result = brief(memory, list(memory.facts.values()))
    assert any(obj == "RabbitMQ" for _, obj in result.superseded)
    assert all(obj != "RabbitMQ" for _, obj, _ in result.decisions)


def test_brief_surfaces_what_memory_is_unsure_about(memory):
    """A tidy summary that hides uncertainty is worse than no summary."""
    result = brief(memory, list(memory.facts.values()))
    assert result.open_questions
    assert "WHAT MEMORY IS UNSURE ABOUT" in result.render()


def test_brief_orders_decisions_by_support_not_alphabetically(memory):
    result = brief(memory, list(memory.facts.values()))
    supports = [s for _, _, s in result.decisions]
    assert supports == sorted(supports, reverse=True)


def test_empty_memory_briefs_honestly():
    assert brief(InMemoryProjectMemory(), []).render() == "Memory is empty."


# -- ontology migration -----------------------------------------------------

def test_migrator_with_no_migrations_is_identity():
    migrator = OntologyMigrator()
    assert migrator.canonical(Predicate.SELECTED) is Predicate.SELECTED
    assert migrator.equivalents(Predicate.SELECTED) == {Predicate.SELECTED}


def test_rename_makes_old_and_new_predicates_equivalent():
    migrator = OntologyMigrator((
        PredicateMigration(Predicate.REJECTED, Predicate.DEPRECATED,
                           OntologyVersion.V1_0, "test rename"),
    ))
    assert migrator.canonical(Predicate.REJECTED) is Predicate.DEPRECATED
    assert migrator.equivalents(Predicate.DEPRECATED) == {
        Predicate.DEPRECATED, Predicate.REJECTED
    }


def test_predicate_filters_widen_across_renames():
    migrator = OntologyMigrator((
        PredicateMigration(Predicate.REJECTED, Predicate.DEPRECATED,
                           OntologyVersion.V1_0),
    ))
    widened = migrator.expand((Predicate.DEPRECATED,))
    assert set(widened) == {Predicate.DEPRECATED, Predicate.REJECTED}


def test_rename_cycles_terminate():
    """A rename cycle is a taxonomy bug, not a reason to hang."""
    migrator = OntologyMigrator((
        PredicateMigration(Predicate.USES, Predicate.CALLS, OntologyVersion.V1_0),
        PredicateMigration(Predicate.CALLS, Predicate.USES, OntologyVersion.V1_0),
    ))
    assert migrator.canonical(Predicate.USES) in (Predicate.USES, Predicate.CALLS)


def test_plan_reports_impact_without_writing(memory):
    before = memory.stats()
    impact = OntologyMigrator().plan(list(memory.facts.values()), OntologyVersion.V1_0)
    assert isinstance(impact, MigrationImpact)
    assert memory.stats() == before, "planning must not touch memory"


def test_plan_explains_that_facts_are_not_rewritten():
    migrator = OntologyMigrator((
        PredicateMigration(Predicate.SELECTED, Predicate.DEPRECATED,
                           OntologyVersion.V1_0),
    ))
    store = InMemoryProjectMemory()
    Ingestor(memory=store).ingest_scenario(QUEUE)
    impact = migrator.plan(list(store.facts.values()), OntologyVersion.V1_0)
    assert impact.affected_facts > 0
    assert any("NOT rewritten" in n for n in impact.notes)


def test_migrator_has_no_apply_method():
    """There is nothing to apply; facts are never rewritten."""
    assert not hasattr(OntologyMigrator, "apply")
