Add faceted search to the storefront.

The storefront now queries Elasticsearch rather than Postgres for search results.
Facet counts come from the same query.

Trade-off: the storefront is now sensitive to index staleness, which is bounded by
indexer lag rather than by transaction commit.
