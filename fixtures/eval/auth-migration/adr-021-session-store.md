# ADR 021: Session Storage

## Status
Accepted

## Context
Sessions are currently held in process memory, so a rolling deploy logs everyone out.

## Decision
Use Redis for session storage.

## Consequences
Redis becomes a hard runtime dependency for the web tier. The web tier depends on Redis.
