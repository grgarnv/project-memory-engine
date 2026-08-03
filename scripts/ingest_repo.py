"""
Ingest this repository's own history into project memory.

The fixtures were written by someone who knew the pattern table. This script
points the engine at documents nobody wrote for it: the RFCs, the findings, the
changelog, and the commit log. Whatever it gets wrong here is a real defect
class rather than an artefact of a friendly corpus.

    python3 scripts/ingest_repo.py [--db project.db] [--ask ENTITY]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory_engine.ingest import Ingestor, load_artifact
from memory_engine.ir import Artifact, ArtifactType, deterministic_id
from memory_engine.resolve import BeliefResolver, render
from memory_engine.store import InMemoryProjectMemory, SQLiteProjectMemory

ROOT = Path(__file__).resolve().parent.parent

# Which documents count as what kind of evidence. RFCs are approved decisions;
# findings and changelog are records; the README is descriptive.
DOC_SOURCES: tuple[tuple[str, ArtifactType], ...] = (
    ("docs/rfcs/*.md", ArtifactType.ADR),
    ("docs/findings/*.md", ArtifactType.DOCUMENT),
    ("docs/architecture.md", ArtifactType.DOCUMENT),
    ("docs/roadmap.md", ArtifactType.DOCUMENT),
    ("docs/changelog.md", ArtifactType.DOCUMENT),
    ("README.md", ArtifactType.DOCUMENT),
    ("CONTRIBUTING.md", ArtifactType.DOCUMENT),
)


def git_commits(limit: int = 200) -> list[Artifact]:
    """Commit messages as artifacts, dated by author date."""
    try:
        raw = subprocess.run(
            ["git", "log", f"-{limit}", "--format=%H%x00%aI%x00%B%x1e"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    artifacts = []
    for record in raw.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        sha, date, body = record.split("\x00", 2)
        artifacts.append(
            Artifact(
                id=deterministic_id("artifact", "commit", sha),
                type=ArtifactType.COMMIT,
                content=body.strip(),
                recorded_at=date[:10],
                metadata={"sha": sha[:12]},
            )
        )
    return artifacts


def doc_artifacts() -> list[Artifact]:
    """Documents, dated by the last commit that touched them."""
    artifacts = []
    for pattern, atype in DOC_SOURCES:
        for path in sorted(ROOT.glob(pattern)):
            try:
                when = subprocess.run(
                    ["git", "log", "-1", "--format=%aI", "--", str(path.relative_to(ROOT))],
                    cwd=ROOT, capture_output=True, text=True, check=True,
                ).stdout.strip()[:10]
            except (subprocess.CalledProcessError, FileNotFoundError):
                when = ""
            artifacts.append(load_artifact(path, atype, when))
    return artifacts


def report(memory, results) -> None:
    facts = list(memory.facts.values())
    domain = [f for f in facts if not f.is_artifact_scoped]
    artifact_scoped = len(facts) - len(domain)

    print("=" * 78)
    print("CORPUS")
    print("=" * 78)
    print(f"  artifacts ingested : {len(results)}")
    print(f"  compiler facts     : {sum(len(r.compiled.facts) for r in results)}")
    print(f"  entities bound     : {len(memory.entities)}")
    print(f"  persisted facts    : {len(facts)}")
    print(f"    domain-anchored  : {len(domain)}")
    print(f"    artifact-scoped  : {artifact_scoped}")
    print(f"  evidence records   : {len(memory.evidence)}")
    print(f"  supersessions      : {len(memory.supersessions)}")
    print(f"  conflicts          : {len(memory.conflicts)}")

    print("\n" + "=" * 78)
    print("YIELD  (did anything become knowledge?)")
    print("=" * 78)
    ratio = len(domain) / len(facts) if facts else 0
    print(f"  domain fact ratio  : {ratio:.1%}")
    reuse = Counter(e.persisted_fact_id for e in memory.evidence)
    corroborated = sum(1 for c in reuse.values() if c > 1)
    print(f"  facts with >1 evidence record : {corroborated} of {len(facts)}")

    print("\n" + "=" * 78)
    print("FRAGMENTATION  (how many names denote one concept?)")
    print("=" * 78)
    names = sorted(b.local_canonical_name for b in memory.entities.values())
    clusters: dict[str, list[str]] = {}
    for name in names:
        head = re.sub(r"[^a-z0-9]", "", name.lower().split()[-1])
        clusters.setdefault(head, []).append(name)
    for head, group in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        if len(group) > 1:
            print(f"  {head:<20} {group}")

    print("\n" + "=" * 78)
    print("PREDICATE DISTRIBUTION")
    print("=" * 78)
    for pred, count in Counter(f.predicate.value for f in facts).most_common():
        print(f"  {pred:<16} {count}")

    print("\n" + "=" * 78)
    print("DOMAIN FACTS  (a sample of what actually entered the graph)")
    print("=" * 78)
    for fact in domain[:40]:
        s = memory.label_for_ref(fact.subject_ref)
        o = memory.label_for_ref(fact.object_ref)
        o = o if len(o) < 50 else o[:47] + "..."
        print(f"  {s:<34} --{fact.predicate.value:<12}--> {o}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--ask", action="append", default=[])
    args = parser.parse_args()

    memory = SQLiteProjectMemory(args.db) if args.db else InMemoryProjectMemory()
    ingestor = Ingestor(memory=memory)

    artifacts = doc_artifacts() + git_commits()
    results = [ingestor.ingest(a) for a in artifacts]

    report(memory, results)

    for entity in args.ask:
        print("\n" + "-" * 78)
        print(render(BeliefResolver(memory).explain(entity)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
