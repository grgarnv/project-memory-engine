"""
LLM providers.

Quarantined in its own package for a reason: an LLM in the compiler makes
compilation reproducible only relative to (model, prompt, temperature,
provider), not absolutely. Anything importing this module inherits that
qualification. Nothing in linker/, store/, or resolve/ may import it - see
tests/test_import_boundaries.py.
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod

from memory_engine.compiler.extractors.base import CURRENT_CHANGE, StatementExtractor
from memory_engine.ir import Segment, Statement


class LLMProvider(ABC):
    """
    Abstract interface for LLM providers.
    Encapsulates network API calls and credentials so LLMStatementExtractor
    remains provider-agnostic.
    """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Execute prompt against the LLM provider and return raw text response."""


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key missing. Set OPENAI_API_KEY or LLM_API_KEY environment variable."
            )
        self.model = model

    def generate(self, prompt: str) -> str:
        import urllib.request

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]


class GeminiProvider(LLMProvider):
    """Google Gemini API provider implementation."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key missing. Set GEMINI_API_KEY or LLM_API_KEY environment variable."
            )
        self.model = model

    def generate(self, prompt: str) -> str:
        import urllib.request

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]


class GenericHTTPProvider(LLMProvider):
    """Generic HTTP endpoint provider implementation."""

    def __init__(self, endpoint_url: str, api_key: str | None = None):
        self.endpoint_url = endpoint_url
        self.api_key = api_key or os.environ.get("LLM_API_KEY")

    def generate(self, prompt: str) -> str:
        import urllib.request

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"prompt": prompt}
        req = urllib.request.Request(
            self.endpoint_url, data=json.dumps(payload).encode("utf-8"), headers=headers
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response") or data.get("text", "")


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for deterministic offline testing."""

    def __init__(self, canned_response: str | None = None):
        self.canned_response = canned_response or json.dumps(
            [
                {
                    "subject": CURRENT_CHANGE,
                    "predicate": "description",
                    "target": "Extracted via LLM",
                }
            ]
        )

    def generate(self, prompt: str) -> str:
        return self.canned_response


class LLMStatementExtractor(StatementExtractor):
    """
    LLM-backed statement extractor.

    Receives an LLMProvider instance (OpenAIProvider, GeminiProvider,
    GenericHTTPProvider, MockLLMProvider, etc.). Formulates deterministic
    prompts and parses returned JSON into Statement objects without provider lock-in.
    """

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or MockLLMProvider()

    def extract(self, segment: Segment) -> list[Statement]:
        prompt = (
            "Extract binary statements (subject, predicate, target) from the following software text snippet.\n"
            "Return ONLY a JSON array of objects with keys 'subject', 'predicate', and 'target'. Do not include markdown code block markers.\n\n"
            f"Text snippet: {segment.text}"
        )
        response_text = self.provider.generate(prompt).strip()

        if response_text.startswith("```"):
            response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
            response_text = re.sub(r"\n?```$", "", response_text)

        try:
            items = json.loads(response_text)
            statements = []
            for item in items:
                statements.append(
                    Statement(
                        subject=item.get("subject", CURRENT_CHANGE),
                        predicate=item.get("predicate", "description"),
                        target=item.get("target", segment.text),
                        observation_id=segment.observation_id,
                    )
                )
            return statements
        except Exception:
            return [
                Statement(
                    subject=CURRENT_CHANGE,
                    predicate="description",
                    target=segment.text,
                    observation_id=segment.observation_id,
                )
            ]
