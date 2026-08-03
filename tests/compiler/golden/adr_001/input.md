# ADR 001: Move JWT Validation to Gateway

## Status
Accepted

## Context
Every service currently duplicates authentication logic.

## Decision
Move JWT validation into the API Gateway.

## Consequences
Gateway complexity increases.
