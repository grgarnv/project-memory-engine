from pathlib import Path

from memory_engine.ir import Artifact, ArtifactType
from memory_engine.pipeline import MemoryCompiler


def main():
    path = Path("samples/sample_pr.md")
    artifact = Artifact(type=ArtifactType.PR, source=path, content=path.read_text())

    result = MemoryCompiler().compile(artifact)

    print(f"Observations : {len(result['observations'])}")
    print(f"Segments     : {len(result['segments'])}")
    print(f"Statements   : {len(result['statements'])}")
    print(f"Entities     : {len(result['entities'])}")
    print(f"Facts        : {len(result['facts'])}")
    print(f"Claims       : {len(result['claims'])}")

    print("\nEntities:")
    for entity in result["entities"]:
        print(f"  {entity.canonical_name} ({entity.entity_type.value})")

    print("\nFacts:")
    for i, fact in enumerate(result["facts"], start=1):
        print(f"  [{i}] {fact.subject} --{fact.predicate.value}--> {fact.object}")


if __name__ == "__main__":
    main()
