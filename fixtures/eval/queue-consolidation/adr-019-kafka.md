# ADR 019: Consolidate on Kafka

## Status
Accepted

## Context
The analytics pipeline already runs on Kafka, so we operate two brokers for no
particular reason. Retention semantics differ, which has bitten us twice.

## Decision
Use Kafka for asynchronous messaging.

Kafka now replaces RabbitMQ.

## Consequences
The order service depends on Kafka. Migration is not free; consumers must be rewritten.
