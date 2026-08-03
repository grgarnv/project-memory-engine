"""
GitHub pull requests and issues.

The decision is usually not in the PR title. It is in the review thread, three
comments down, where someone said "we can't use X here because Y". This adapter
pulls the body plus review comments and treats the whole conversation as one
artifact, because splitting it would lose the thread that makes it legible.

Incremental by `updated_at`, which is what the GitHub API paginates on. A PR
that gets a new comment is re-fetched and re-ingested; content addressing makes
the unchanged parts a no-op and the new comment lands as fresh evidence.

Auth comes from the environment. This adapter never takes a token as an
argument, so a token cannot end up in a log line, a config file, or a stack
trace.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Iterator

from memory_engine.ir import Artifact, ArtifactType, deterministic_id
from memory_engine.sources.base import ArtifactSource

API = "https://api.github.com"
PAGE_SIZE = 50


class GitHubError(RuntimeError):
    pass


class GitHubSource(ArtifactSource):
    def __init__(self, owner: str, repo: str, kind: str = "pulls",
                 include_comments: bool = True, max_items: int = 0,
                 opener=None):
        if kind not in ("pulls", "issues"):
            raise ValueError("kind must be 'pulls' or 'issues'")
        self.owner = owner
        self.repo = repo
        self.kind = kind
        self.include_comments = include_comments
        self.max_items = max_items
        self._open = opener or self._http_get  # injectable, so tests need no network

    @property
    def source_id(self) -> str:
        return f"github:{self.owner}/{self.repo}:{self.kind}"

    # -- transport ----------------------------------------------------------

    @staticmethod
    def _token() -> str:
        return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

    def _http_get(self, url: str) -> list | dict:
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "project-memory-engine",
            **({"Authorization": f"Bearer {self._token()}"} if self._token() else {}),
        })
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                # 403 with a reset header is rate limiting, not authorization.
                # Backing off is correct; retrying immediately gets you banned.
                if exc.code in (403, 429) and attempt < 3:
                    reset = exc.headers.get("X-RateLimit-Reset")
                    wait = max(1, int(reset) - int(time.time())) if reset else 2 ** attempt
                    time.sleep(min(wait, 60))
                    continue
                if exc.code == 401:
                    raise GitHubError(
                        "GitHub rejected the credentials. Set GITHUB_TOKEN."
                    ) from exc
                raise GitHubError(f"GitHub returned {exc.code} for {url}") from exc
        raise GitHubError(f"Gave up after rate-limit retries: {url}")

    # -- fetch --------------------------------------------------------------

    def _comments(self, number: int) -> list[str]:
        if not self.include_comments:
            return []
        bodies: list[str] = []
        for path in (f"issues/{number}/comments", f"pulls/{number}/comments"):
            if path.startswith("pulls") and self.kind != "pulls":
                continue
            try:
                for comment in self._open(f"{API}/repos/{self.owner}/{self.repo}/{path}"):
                    body = (comment.get("body") or "").strip()
                    if body:
                        bodies.append(f"{comment.get('user', {}).get('login', 'someone')}: {body}")
            except GitHubError:
                continue  # a missing comment endpoint must not lose the PR itself
        return bodies

    def fetch(self, since: str = "") -> Iterator[Artifact]:
        page = 1
        produced = 0
        while True:
            url = (
                f"{API}/repos/{self.owner}/{self.repo}/{self.kind}"
                f"?state=all&sort=updated&direction=asc&per_page={PAGE_SIZE}&page={page}"
            )
            batch = self._open(url)
            if not batch:
                return

            for item in batch:
                updated = (item.get("updated_at") or "")[:10]
                if since and updated and updated < since:
                    continue
                if self.kind == "pulls" and item.get("pull_request") is None and "number" not in item:
                    continue

                number = item["number"]
                parts = [item.get("title", ""), (item.get("body") or "").strip()]
                parts.extend(self._comments(number))
                content = "\n\n".join(p for p in parts if p)
                if not content.strip():
                    continue

                atype = ArtifactType.PR if self.kind == "pulls" else ArtifactType.ISSUE
                yield Artifact(
                    id=deterministic_id("artifact", atype.value, content),
                    type=atype,
                    content=content,
                    recorded_at=(item.get("created_at") or updated)[:10],
                    metadata={"number": number, "updated_at": updated,
                              "url": item.get("html_url", "")},
                )
                produced += 1
                if self.max_items and produced >= self.max_items:
                    return

            if len(batch) < PAGE_SIZE:
                return
            page += 1

    def watermark_for(self, artifact: Artifact) -> str:
        return artifact.metadata.get("updated_at", artifact.recorded_at)
