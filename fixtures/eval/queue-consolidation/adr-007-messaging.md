# ADR 007: Asynchronous Messaging

## Status
Superseded by ADR 019

## Context
Order processing and notification delivery both need to happen off the request path.
Two teams have independently reached for different tools.

## Decision
Use RabbitMQ for asynchronous messaging.

## Consequences
We take on a broker that nobody on call has operated before.
