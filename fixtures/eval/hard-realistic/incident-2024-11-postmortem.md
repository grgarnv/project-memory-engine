# Postmortem: Search outage, 12 Nov 2024

The Elasticsearch cluster lost quorum for 43 minutes. Because the storefront depends
on Elasticsearch for all search traffic, product search returned errors for the whole
window.

Action item: the storefront should fall back to Postgres when the index is
unavailable. This has not been implemented.
