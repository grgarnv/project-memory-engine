# ADR 102: Search Infrastructure

## Status
Accepted

## Context
Product search currently hits Postgres directly with ILIKE queries. At 40k SKUs this
is already marginal, and the merchandising team wants faceting, which we cannot do
without either a lot of denormalisation or a purpose-built index.

We looked at Elasticsearch, Typesense, and staying on Postgres with pg_trgm plus
materialised views.

## Decision
We're going with Elasticsearch for product search. Typesense was attractive
operationally but the team has no experience with it, and the managed offering
wasn't available in our region at the time of writing.

## Consequences
Another stateful system in the critical path. Search availability is now coupled to
cluster health, and the indexer becomes a thing someone has to own.
