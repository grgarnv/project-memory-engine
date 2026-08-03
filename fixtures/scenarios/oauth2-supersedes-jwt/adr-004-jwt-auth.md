# ADR 004: Service-to-Service Authentication

## Status
Superseded

## Context
Internal services need to authenticate calls between each other.

## Decision
Use JWT for service-to-service authentication.

## Consequences
Token revocation is not possible before expiry.
