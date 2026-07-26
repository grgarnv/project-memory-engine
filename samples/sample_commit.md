Add retry logic to payments client

Payments provider intermittently returns 5xx errors.

This adds exponential backoff with 3 retries.
