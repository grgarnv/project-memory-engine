Port the order consumer to Kafka.

Reason:
The order service uses Kafka, and the notification worker uses Kafka.

Trade-off:
Consumer rebalancing is harder to reason about than acknowledgements were.
