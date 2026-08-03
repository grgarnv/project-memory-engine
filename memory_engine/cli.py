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
from memory_engine.resolve import BeliefResolver, render
from memory_engine.store import InMemoryProjectMemory, SQLiteProjectMemory


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

    p_stats = sub.add_parser("stats", help="counts of what is in memory")
    p_stats.add_argument("--db", help="SQLite file")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
