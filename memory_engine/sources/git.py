"""
Git history as artifacts.

Commit messages are the highest-volume and lowest-authority decision record a
project has. They are also the only one that is guaranteed complete: every
project has a git log, and not every project has ADRs.

Incremental by commit SHA. `git log <sha>..HEAD` is exactly the primitive
needed, so the watermark is the last SHA seen rather than a timestamp - commit
dates are not monotonic across merges and would skip work.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterator

from memory_engine.ir import Artifact, ArtifactType, deterministic_id
from memory_engine.sources.base import ArtifactSource

# Unit separator, not NUL: a format string is passed through argv, and a null
# byte cannot survive that. Both are chosen because neither appears in commit
# messages.
_RECORD = "\x1e"
_FIELD = "\x1f"

# Commits that assert nothing. Cheap to skip, and they otherwise dominate the
# corpus with facts nobody wants.
_NOISE_PREFIXES = (
    "merge branch", "merge pull request", "merge remote",
    "bump ", "chore(deps)", "revert \"", "wip", "fixup!", "squash!",
)


class GitSource(ArtifactSource):
    def __init__(self, repo: str | Path = ".", branch: str = "HEAD",
                 include_noise: bool = False, max_commits: int = 0):
        self.repo = Path(repo)
        self.branch = branch
        self.include_noise = include_noise
        self.max_commits = max_commits

    @property
    def source_id(self) -> str:
        return f"git:{self.repo.resolve()}:{self.branch}"

    def _log(self, since: str) -> str:
        rev = f"{since}..{self.branch}" if since else self.branch
        cmd = ["git", "log", rev, f"--format=%H{_FIELD}%aI{_FIELD}%an{_FIELD}%B{_RECORD}",
               "--reverse"]
        if self.max_commits:
            cmd.insert(2, f"-{self.max_commits}")
        try:
            return subprocess.run(cmd, cwd=self.repo, capture_output=True,
                                  text=True, check=True).stdout
        except subprocess.CalledProcessError:
            # An unknown watermark SHA means history was rewritten. Falling back
            # to a full read is correct: content addressing makes the overlap a
            # no-op, so the cost is time, not duplicates.
            if since:
                return self._log("")
            raise
        except FileNotFoundError:
            return ""

    @staticmethod
    def _is_noise(message: str) -> bool:
        first = message.strip().splitlines()[0].lower() if message.strip() else ""
        return any(first.startswith(p) for p in _NOISE_PREFIXES)

    def fetch(self, since: str = "") -> Iterator[Artifact]:
        for record in self._log(since).split(_RECORD):
            record = record.strip()
            if not record:
                continue
            try:
                sha, when, author, body = record.split(_FIELD, 3)
            except ValueError:
                continue
            body = body.strip()
            if not body:
                continue
            if not self.include_noise and self._is_noise(body):
                continue
            yield Artifact(
                id=deterministic_id("artifact", "commit", sha),
                type=ArtifactType.COMMIT,
                content=body,
                recorded_at=when[:10],
                metadata={"sha": sha, "author": author},
            )

    def watermark_for(self, artifact: Artifact) -> str:
        return artifact.metadata.get("sha", "")
