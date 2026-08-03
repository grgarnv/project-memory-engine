# RFC 31: Indexing Pipeline

The catalogue service publishes change events; the indexer consumes them and writes
into Elasticsearch. Nothing else should write to the index directly — if you need
data in there, emit an event.

The indexer is stateless and can be scaled horizontally.

Note that the catalogue service does not talk to Elasticsearch at all. That coupling
was deliberately avoided.
