# Ephemeral synthetic workflow worker

This repository provides a small authenticated HTTP worker for testing workflow execution across independently hosted Linux nodes. Test payloads are synthetic.

The worker stores test files in memory, checks task inputs, waits for a bounded synthetic service time, and emits synthetic outputs. Every endpoint requires a bearer token supplied at runtime.

## Worker API

- GET /health checks readiness.
- GET /identity returns the process identity, software version, a boot-ID hash, and the GitHub run identifier.
- POST /reset clears the in-memory test store.
- POST /file/ID stores a test file; GET /file/ID retrieves it.
- POST /probe stores a probe payload.
- POST /run accepts inputs, outputs, and seconds as a JSON test task.

The GitHub Actions workflow starts the worker in a container limited to one CPU and 512 MiB, opens a temporary Cloudflare Quick Tunnel, and records its URL in .sessions/RUN_ID.json. It remains available for up to 40 minutes after setup, with a 45-minute job timeout. Cancelling the job ends the worker.

Set the repository secret WORKER_TOKEN to a fresh random value of at least 32 characters before dispatch. The token is supplied to the container at runtime. The published session record contains the endpoint URL and run ID. Access requires the bearer token.

The workflow uses a standard Ubuntu runner, downloads a checksum-pinned cloudflared binary from the official release, and uses a pinned Python base image. It does not upload Actions artifacts or configure an Actions cache.

The source package can be reviewed independently before creating the repository. Its public files contain the worker, Docker build, and workflow described here.
