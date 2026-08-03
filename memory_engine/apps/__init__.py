"""
Applications built on the resolver.

These are consumers, not infrastructure. Each one answers a question by asking
memory, and none of them may reach past the resolver into the linker or a store
- if an application needs a fact the resolver cannot produce, the gap belongs in
the read path where every application benefits, not in the application.
"""
from memory_engine.apps.compliance import ComplianceEngine, Violation
from memory_engine.apps.onboarding import OnboardingBrief, brief

__all__ = ["ComplianceEngine", "Violation", "OnboardingBrief", "brief"]
