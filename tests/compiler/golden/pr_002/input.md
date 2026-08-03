# Pull Request

Add retry logic to the payments client.

Currently a single network blip fails the whole checkout flow.

Reason:
Payments provider has intermittent 5xx errors under load.

Trade-off:
Checkout latency increases slightly on retry.
