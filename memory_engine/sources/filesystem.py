"""
A directory of documents.

ADRs, RFCs, and design docs usually live in a folder. Dates come from git when
the directory is inside a repository, because a file's mtime is when it was last
checked out, not when the decision was made - and getting that wrong feeds the
ordering rules garbage.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterator

from memory_engine.ingest import infer_artifact_type
from memory_engine.ir import Artifact, ArtifactType, deterministic_id
from memory_engine.sources.base import ArtifactSource


class FilesystemSource(ArtifactSource):
    def __init__(self, root: str | Path, pattern: str = "**/*.md",
                 artifact_type: ArtifactType | None = None):
        self.root = Path(root)
        self.pattern = pattern
        self.artifact_type = artifact_type

    @property
    def source_id(self) -> str:
        return f"fs:{self.root.resolve()}:{self.pattern}"

    def _authored_at(self, path: Path) -> str:
        """First commit that added the file - when the decision was written."""
        try:
            out = subprocess.run(
                ["git", "log", "--diff-filter=A", "--format=%aI", "-1", "--", path.name],
                cwd=path.parent, capture_output=True, text=True, check=True,
            ).stdout.strip()
            if out:
                return out[:10]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return ""

    def fetch(self, since: str = "") -> Iterator[Artifact]:
        for path in sorted(self.root.glob(self.pattern)):
            if not path.is_file():
                continue
            content = path.read_text(errors="replace")
            when = self._authored_at(path)
            if since and when and when <= since:
                continue
            atype = self.artifact_type or infer_artifact_type(path)
            yield Artifact(
                id=deterministic_id("artifact", atype.value, content),
                type=atype,
                source=path,
                content=content,
                recorded_at=when,
                metadata={"path": str(path)},
            )
