Migrate the session store to PostgreSQL.

Reason:
Use PostgreSQL for session storage, so that sessions survive a deploy without a second datastore.

Trade-off:
Session reads get slower under load.
