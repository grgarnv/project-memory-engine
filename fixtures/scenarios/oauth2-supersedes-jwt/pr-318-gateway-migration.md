Migrate the API Gateway to OAuth2.

Reason:
Use OAuth2 for service-to-service authentication, because it supports token revocation.

Trade-off:
Adds a network hop to the token service on every request.
