# ADR 034: Move Sessions to PostgreSQL

## Status
Accepted

## Context
Operating a second datastore for one feature has not paid off, and the Redis instance
is the only component without a backup story.

## Decision
Use PostgreSQL for session storage.

## Consequences
Session reads get slower. The web tier depends on PostgreSQL.
