# ADR 012: Replace JWT with OAuth2 Client Credentials

## Status
Accepted

## Context
JWT cannot be revoked before expiry, which blocks incident response.

## Decision
Use OAuth2 for service-to-service authentication.

## Consequences
OAuth2 introduces a dependency on the token service.
