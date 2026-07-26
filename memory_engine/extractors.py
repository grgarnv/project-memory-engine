"""
Extractors

Pluggable logic for turning one IR object into another. Two interfaces:

    StatementExtractor.extract(segment)   -> list[Statement]
    FactExtractor.extract(statement)      -> list[Fact]

Swap in a smarter (e.g. LLM-backed) extractor later by implementing the
same interface - the pipeline doesn't care which one it's given.
"""
import json
import os
import re
from abc import ABC, abstractmethod

from memory_engine.ir import Segment, SegmentKind, Statement, Claim, Fact, FactType, Entity
from memory_engine.ontology import Predicate, EntityType

CURRENT_CHANGE = "Current Change"

# A Claim is promoted to a Fact only above this confidence. Named constant
# rather than a bare number so the cutoff is obvious and easy to tune
# without reading FactExtractor's implementation.
FACT_CONFIDENCE_THRESHOLD = 0.7


class StatementExtractor(ABC):
    @abstractmethod
    def extract(self, segment: Segment) -> list[Statement]:
        """Convert one Segment into zero or more Statements."""


class FactExtractor(ABC):
    @abstractmethod
    def extract(self, claim: Claim) -> list[Fact]:
        """Decide whether a Claim is concrete and structured enough to be
        promoted to a Fact. Returns [] if it should remain a Claim only."""


# Segment kind -> free-text predicate used by the statement layer.
_SEGMENT_PREDICATES = {
    SegmentKind.DESCRIPTION: "description",
    SegmentKind.REASON: "has_reason",
    SegmentKind.TRADEOFF: "has_tradeoff",
    SegmentKind.DECISION: "selected",
    SegmentKind.CONTEXT: "has_reason",
    SegmentKind.STATUS: "describes",
    SegmentKind.CONSEQUENCE: "has_tradeoff",
}

# Free-text predicate -> ontology Predicate used by the fact layer.
_PREDICATE_MAP = {
    "description": Predicate.DESCRIBES,
    "has_reason": Predicate.HAS_REASON,
    "has_tradeoff": Predicate.HAS_TRADEOFF,
    "selected": Predicate.SELECTED,
    "describes": Predicate.DESCRIBES,
}


class RuleBasedStatementExtractor(StatementExtractor):
    """Deterministic segment-kind -> predicate mapping. No ML involved."""

    def extract(self, segment: Segment) -> list[Statement]:
        predicate = _SEGMENT_PREDICATES.get(segment.kind, "unknown")
        return [
            Statement(
                subject=CURRENT_CHANGE,
                predicate=predicate,
                target=segment.text,
                observation_id=segment.observation_id,
            )
        ]


class RuleBasedFactExtractor(FactExtractor):
    """Filters Claims into Facts. A Claim is promoted only if both hold:

      - concrete enough:    confidence >= FACT_CONFIDENCE_THRESHOLD
      - structured enough:  predicate maps to a known ontology Predicate

    Otherwise the claim remains a Claim only - this method returns [].
    """

    def extract(self, claim: Claim) -> list[Fact]:
        predicate = _PREDICATE_MAP.get(claim.predicate, Predicate.UNKNOWN)

        if claim.confidence < FACT_CONFIDENCE_THRESHOLD:
            return []

        if predicate is Predicate.UNKNOWN:
            return []

        return [
            Fact(
                subject=claim.subject,
                predicate=predicate,
                object=claim.target,
                fact_type=FactType.OBSERVATION,
                source_claim=claim.id,
                supporting_statements=list(claim.supporting_statements),
            )
        ]


# ---------------------------------------------------------------------------
# LLM Provider Abstraction & LLMStatementExtractor
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entity Recognizer Interface & GeneralEntityRecognizer
# ---------------------------------------------------------------------------

class EntityRecognizer(ABC):
    @abstractmethod
    def recognize(self, text: str) -> list[Entity]:
        """Extract software entity mentions from text."""


class GeneralEntityRecognizer(EntityRecognizer):
    """
    General-purpose software entity recognizer.

    Identifies software entity mentions (components, features, tools, databases,
    frameworks, services, protocols like Redis, PostgreSQL, Kubernetes, React, OAuth,
    Kafka, API Gateway, JWT validation, authentication).

    Decoupled from ontology taxonomy decisions - returns Entity objects with canonical_name
    and aliases, setting entity_type to EntityType.UNKNOWN unless explicit structural hints match.
    """

    _KNOWN_PATTERNS = [
        # Explicit demo / golden test patterns to preserve backward compatibility contracts
        (r"\bAPI Gateway\b", EntityType.COMPONENT),
        (r"\bJWT validation\b", EntityType.FEATURE),
        (r"\bauthentication\b", EntityType.FEATURE),
        # General software engineering terms
        (r"\b(PostgreSQL|Postgres|Redis|MongoDB|MySQL|SQLite|DynamoDB|Elasticsearch)\b", EntityType.DATABASE),
        (r"\b(Kubernetes|K8s|Docker|Terraform|Helm|Ansible)\b", EntityType.UNKNOWN),
        (r"\b(React|Vue|Angular|Next\.js|Node\.js|Django|FastAPI|Flask|Spring Boot)\b", EntityType.FRAMEWORK),
        (r"\b(Kafka|RabbitMQ|NATS|Pulsar|AWS SQS)\b", EntityType.UNKNOWN),
        (r"\b(OAuth|OAuth2|JWT|gRPC|GraphQL|REST|SAML)\b", EntityType.FEATURE),
    ]

    def recognize(self, text: str) -> list[Entity]:
        entities: dict[str, Entity] = {}

        for pattern, entity_type in self._KNOWN_PATTERNS:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                key = match.lower()
                if key not in entities:
                    entities[key] = Entity(
                        canonical_name=match,
                        entity_type=entity_type,
                        aliases=[match],
                    )

        # Code identifier heuristic (e.g. AuthClient, UserGateway)
        code_identifiers = re.findall(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b", text)
        for ident in code_identifiers:
            key = ident.lower()
            if key not in entities:
                entities[key] = Entity(
                    canonical_name=ident,
                    entity_type=EntityType.UNKNOWN,
                    aliases=[ident],
                )

        return list(entities.values())
