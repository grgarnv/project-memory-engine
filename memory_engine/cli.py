"""
Command line interface.

    pme compile <file>                     inspect one artifact's compilation
    pme ingest  <path> [--db FILE]         compile + link one file or a directory
    pme ask     <entity> [--db FILE]       what does the project believe about X
    pme stats   [--db FILE]                what is in memory

Without --db, memory is in-process and disappears when the command exits, which
is useful for `pme ingest <dir> --ask <entity>` in one shot. With --db, memory
persists to SQLite and `ask` queries what previous runs accumulated.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from memory_engine.compiler import MemoryCompiler
from memory_engine.ingest import Ingestor, load_artifact
from memory_engine.memory.contracts import ProjectMemory
from memory_engine.resolve import BeliefResolver, ProjectQueries, explain, render
from memory_engine.store import InMemoryProjectMemory, SQLiteProjectMemory


def _all_facts(memory) -> list:
    """Facts from any store, without assuming an in-memory dict."""
    if hasattr(memory, "facts"):
        return list(memory.facts.values())
    rows = memory.conn.execute("SELECT id FROM facts").fetchall()
    return [memory.get_fact(r["id"]) for r in rows]


def _open_memory(db: str | None) -> ProjectMemory:
    return SQLiteProjectMemory(db) if db else InMemoryProjectMemory()


def cmd_compile(args: argparse.Namespace) -> int:
    artifact = load_artifact(args.path)
    result = MemoryCompiler().compile(artifact)

    if args.json:
        print(result.to_json())
        return 0

    print(f"artifact     : {artifact.id}  ({artifact.type.value})")
    print(f"compiler     : {result.compiler_version}  ontology {result.ontology_version.value}")
    print(f"observations : {len(result.observations)}")
    print(f"segments     : {len(result.segments)}")
    print(f"statements   : {len(result.statements)}")
    print(f"claims       : {len(result.claims)}")
    print(f"facts        : {len(result.facts)}")
    print(f"relations    : {len(result.relations)}")

    print("\nentities:")
    for entity in result.entities:
        print(f"  {entity.canonical_name}  ({entity.entity_type.value})")

    print("\nfacts:")
    for i, fact in enumerate(result.facts, 1):
        obj = fact.object if len(fact.object) < 64 else fact.object[:61] + "..."
        print(f"  [{i}] {fact.subject} --{fact.predicate.value}--> {obj}")

    unpromoted = len(result.claims) - len(result.facts)
    if unpromoted:
        print(f"\n{unpromoted} claim(s) not promoted (low confidence or unmapped predicate)")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    memory = _open_memory(args.db)
    ingestor = Ingestor(memory=memory)
    path = Path(args.path)

    results = (
        ingestor.ingest_scenario(path) if path.is_dir()
        else [ingestor.ingest_file(path, recorded_at=args.recorded_at)]
    )

    for result in results:
        print("  " + result.summary)
        for note in result.delta.diagnostics:
            print(f"      ! {note}")

    print("\nmemory:", ", ".join(f"{k}={v}" for k, v in memory.stats().items()))

    if args.ask:
        print()
        print(render(BeliefResolver(memory).explain(args.ask)))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    memory = _open_memory(args.db)
    belief = BeliefResolver(memory).explain(args.entity)
    print(render(belief))
    return 0 if belief.answered else 1


def cmd_stats(args: argparse.Namespace) -> int:
    memory = _open_memory(args.db)
    for key, value in memory.stats().items():
        print(f"{key:<16} {value}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    memory = _open_memory(args.db)
    belief = BeliefResolver(memory).explain(args.entity)
    print(explain(belief))
    return 0 if belief.answered else 1


def cmd_timeline(args: argparse.Namespace) -> int:
    memory = _open_memory(args.db)
    entries = ProjectQueries(memory).timeline(args.entity)
    if not entries:
        print(f"Nothing recorded about {args.entity!r}.")
        return 1
    for entry in entries:
        when = entry.when or "  undated "
        marker = "+" if entry.event == "asserted" else "-"
        print(f"{when}  {marker} {entry.statement}")
        if entry.artifact_id:
            print(f"              via {entry.artifact_type or 'supersession'} "
                  f"{entry.artifact_id[:20]}")
    return 0


def cmd_dependents(args: argparse.Namespace) -> int:
    memory = _open_memory(args.db)
    found = ProjectQueries(memory).dependents(args.entity)
    if not found:
        print(f"Nothing currently recorded as depending on {args.entity!r}.")
        return 1
    print(f"Currently depending on {args.entity}:")
    for dep in found:
        print(f"  {dep.label:<34} ({dep.predicate.value}) "
              f"support={dep.support} across {dep.evidence_count} artifact(s)")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    memory = _open_memory(args.db)
    report = ProjectQueries(memory).health(_all_facts(memory))
    for field_name in ("total_facts", "active_facts", "undated_facts",
                       "single_source_facts", "ingestion_ordered_supersessions",
                       "open_conflicts", "unresolved_literals"):
        print(f"{field_name:<34} {getattr(report, field_name)}")
    for note in report.notes:
        print(f"  ! {note}")
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    from memory_engine.sources import FilesystemSource, GitHubSource, GitSource

    memory = _open_memory(args.db)
    ingestor = Ingestor(memory=memory)

    if args.source.startswith("github://"):
        owner, _, repo = args.source[len("github://"):].partition("/")
        sources = [GitHubSource(owner, repo, kind=k) for k in ("pulls", "issues")]
    elif args.source.startswith("git://"):
        sources = [GitSource(args.source[len("git://"):])]
    else:
        sources = [FilesystemSource(args.source)]

    for source in sources:
        run = ingestor.ingest_source(source, resume=not args.full)
        print("  " + run.summary)
        for note in run.notes:
            print(f"      ! {note}")

    print("\nmemory:", ", ".join(f"{k}={v}" for k, v in memory.stats().items()))
    return 0


def cmd_correct(args: argparse.Namespace) -> int:
    from memory_engine.correction import Correction, CorrectionError, apply_correction

    memory = _open_memory(args.db)
    try:
        apply_correction(memory, Correction(
            fact_id=args.fact_id, author=args.author, reason=args.reason))
    except CorrectionError as exc:
        print(f"Could not record the correction: {exc}")
        return 1
    print(f"Recorded. Fact {args.fact_id} is retired on {args.author}'s authority "
          f"and remains queryable as history.")
    return 0


def cmd_pilot(args: argparse.Namespace) -> int:
    from memory_engine.pilot import run_pilot

    memory = _open_memory(args.db)
    report = run_pilot(memory, args.questions)
    print(report.render())
    return 0 if report.wrong == 0 else 1


def cmd_serve(args: argparse.Namespace) -> int:
    from memory_engine.mcp_server import MemoryMCPServer

    MemoryMCPServer(args.db or "project.db").serve()
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    from memory_engine.apps import brief
    memory = _open_memory(args.db)
    print(brief(memory, _all_facts(memory)).render())
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from memory_engine.apps import ComplianceEngine
    from memory_engine.ontology import Predicate

    memory = _open_memory(args.db)
    proposed = []
    for item in args.relationship:
        try:
            subject, predicate, obj = [p.strip() for p in item.split("|")]
        except ValueError:
            print(f"Expected 'subject|predicate|object', got {item!r}")
            return 2
        proposed.append((subject, Predicate(predicate), obj))

    report = ComplianceEngine(memory).check(proposed)
    print(report.summary())
    return 0 if report.is_compliant else 1


def cmd_migrate(args: argparse.Namespace) -> int:
    from memory_engine.ontology import OntologyVersion
    from memory_engine.ontology_migration import OntologyMigrator

    memory = _open_memory(args.db)
    impact = OntologyMigrator().plan(_all_facts(memory), OntologyVersion(args.to_version))
    print(f"target ontology   {impact.target_version.value}")
    print(f"affected facts    {impact.affected_facts}")
    for change, count in sorted(impact.affected_predicates.items()):
        print(f"  {change}: {count}")
    for note in impact.notes:
        print(f"  ! {note}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from memory_engine.eval import run_all
    from memory_engine.eval.harness import format_report

    results = run_all(args.path)
    if not results:
        print(f"No evaluation cases found under {args.path}")
        return 1
    print(format_report(results))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pme", description=__doc__.strip().splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser("compile", help="compile one artifact and print its IR")
    p_compile.add_argument("path")
    p_compile.add_argument("--json", action="store_true", help="emit the full IR as JSON")
    p_compile.set_defaults(func=cmd_compile)

    p_ingest = sub.add_parser("ingest", help="compile and link a file or scenario directory")
    p_ingest.add_argument("path")
    p_ingest.add_argument("--db", help="SQLite file; omit for ephemeral memory")
    p_ingest.add_argument("--recorded-at", dest="recorded_at", default="",
                          help="ISO-8601 date for a single file")
    p_ingest.add_argument("--ask", help="resolve this entity after ingesting")
    p_ingest.set_defaults(func=cmd_ingest)

    p_ask = sub.add_parser("ask", help="what does the project believe about an entity")
    p_ask.add_argument("entity")
    p_ask.add_argument("--db", help="SQLite file")
    p_ask.set_defaults(func=cmd_ask)

    p_explain = sub.add_parser("explain", help="prose answer about an entity")
    p_explain.add_argument("entity")
    p_explain.add_argument("--db")
    p_explain.set_defaults(func=cmd_explain)

    p_timeline = sub.add_parser("timeline", help="everything recorded about an entity, in order")
    p_timeline.add_argument("entity")
    p_timeline.add_argument("--db")
    p_timeline.set_defaults(func=cmd_timeline)

    p_deps = sub.add_parser("dependents", help="what currently relies on an entity")
    p_deps.add_argument("entity")
    p_deps.add_argument("--db")
    p_deps.set_defaults(func=cmd_dependents)

    p_health = sub.add_parser("health", help="where this knowledge base is weak")
    p_health.add_argument("--db")
    p_health.set_defaults(func=cmd_health)

    p_pull = sub.add_parser("pull", help="ingest from a real source, incrementally")
    p_pull.add_argument("source", help="a path, git://<path>, or github://<owner>/<repo>")
    p_pull.add_argument("--db")
    p_pull.add_argument("--full", action="store_true", help="ignore the watermark")
    p_pull.set_defaults(func=cmd_pull)

    p_correct = sub.add_parser("correct", help="record that a fact is wrong")
    p_correct.add_argument("fact_id")
    p_correct.add_argument("--author", required=True)
    p_correct.add_argument("--reason", required=True)
    p_correct.add_argument("--db")
    p_correct.set_defaults(func=cmd_correct)

    p_pilot = sub.add_parser("pilot", help="score memory against real questions")
    p_pilot.add_argument("questions")
    p_pilot.add_argument("--db")
    p_pilot.set_defaults(func=cmd_pilot)

    p_serve = sub.add_parser("serve", help="run the MCP server over stdio")
    p_serve.add_argument("--db")
    p_serve.set_defaults(func=cmd_serve)

    p_brief = sub.add_parser("brief", help="onboarding overview from accumulated memory")
    p_brief.add_argument("--db")
    p_brief.set_defaults(func=cmd_brief)

    p_check = sub.add_parser("check", help="check relationships against recorded constraints")
    p_check.add_argument("relationship", nargs="+",
                         help="'subject|predicate|object', e.g. 'order service|uses|RabbitMQ'")
    p_check.add_argument("--db")
    p_check.set_defaults(func=cmd_check)

    p_migrate = sub.add_parser("migrate", help="report the impact of an ontology version bump")
    p_migrate.add_argument("--to", dest="to_version", default="1.0")
    p_migrate.add_argument("--db")
    p_migrate.set_defaults(func=cmd_migrate)

    p_eval = sub.add_parser("eval", help="extraction precision and recall against labels")
    p_eval.add_argument("path", nargs="?", default="fixtures/eval")
    p_eval.set_defaults(func=cmd_eval)

    p_stats = sub.add_parser("stats", help="counts of what is in memory")
    p_stats.add_argument("--db", help="SQLite file")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
