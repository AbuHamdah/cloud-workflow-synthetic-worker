# Bounded real-application test worker

This generic worker executes allow-listed Montage and MAQ operations on supplied
test objects. It contains no paper, author information, application input data,
runtime credentials, or scientific results. The original synthetic worker remains
unchanged on the repository's main branch.

The proposed publication is a separate `real-applications` branch containing only
these five files: worker.py, Dockerfile, .dockerignore, README.md, and
.github/workflows/worker.yml. The workflow uses a standard hosted Ubuntu runner,
one-CPU/512-MiB container, an authenticated temporary tunnel and bounded lifetime.
It records a temporary endpoint in .sessions on that branch. No paid service or
payment card is used. The coordinator cancels the job after collection and deletes
the runtime secret; the workflow also has a hard timeout and unconditional cleanup.

Supported operations: mProject; mImgtbl + mAdd; MAQ fasta2bfa, fastq2bfq, map
(fixed random seed), mapmerge, mapview and depth-only pileup. There is no shell or
arbitrary executable/argument endpoint. Every request requires a bearer token of
at least 32 characters. File names are restricted to simple basenames. Requests
are capped at 64 MiB, stored objects at 320 MiB, and each tool invocation at 120 s.
Requests may use either fresh or persistent HTTP/1.1 client connections.

`/identity` records source hash, package versions, quota and hashed kernel boot ID.
`/run` records tool argv, exit status, wall time, CPU time, peak process RSS and
output sizes/SHA-256 values. Runtime token files belong only to the coordinator's
private temporary directory and must never be committed.

Inputs are supplied by a separate experimental client. MAQ use with generated
sequence reads validates computational kernels, not biological inference. Montage
subworkflows without background matching are not full production mosaic pipelines.
