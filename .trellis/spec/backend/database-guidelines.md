# Database Guidelines

Version 1 has no database, ORM, migrations, Redis, object storage, or persistent job queue. Cache, rate, admission, and in-flight state are bounded and process-local. A process restart clears them.

Adding persistence or multiple workers requires a separate design for shared limits, expiry, retention, and secret handling.
