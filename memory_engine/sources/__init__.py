"""
Ingestion sources.

`scripts/ingest_repo.py` reads local markdown, which is fine for a demo and
useless against a real repository. These adapters pull from where decisions
actually live, and they are incremental: artifact IDs are content-addressed so
re-ingesting is SAFE, but re-reading forty thousand commits nightly is not
sensible. Each source records a watermark.

Every adapter yields plain `Artifact` objects. Nothing here knows about the
compiler, the linker, or memory - it converts a source into artifacts and stops.
"""
from memory_engine.sources.base import ArtifactSource, SourceRun
from memory_engine.sources.filesystem import FilesystemSource
from memory_engine.sources.git import GitSource
from memory_engine.sources.github import GitHubSource

__all__ = [
    "ArtifactSource",
    "SourceRun",
    "FilesystemSource",
    "GitSource",
    "GitHubSource",
]
