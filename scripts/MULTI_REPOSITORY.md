# Repeat the bounded repository checks

The default coordinator selects the exact commits in `source-lock.template.json`.
In a Git checkout, `python3 scripts/hydrate-sources.py` verifies pins and assembles source
bytes before the network-disabled calculation container starts. Local validation
can use `--local-root ../component-repositories`; the coordinator must be clean
at its actual committed executable revision. `coordinator-origin.json` binds that
revision to the archived coordinator source bytes. This is separate from a later
commit delivering generated site files. Extracted portable archives already carry
verified snapshots: use `python3 scripts/hydrate-sources.py --if-needed` to check
them without a Git checkout or a new network retrieval.

The optional `Dockerfile` embeds the preserved monorepo compatibility mode.
Default split execution uses the SPC image with the hydrated checkout mounted.

Run `python3 scripts/check-multi-repository.py --plan` to inspect the finite
MR-01–08 inventory without calculations. Numerical execution requires the same
preserved SPC image and a fresh output directory. The parent supplies a pinned
monorepo reference and separately hydrated validation source locks. For complete
offline MR-01–08 repetition, a companion archive must include that reference, its
manifest, and both variant snapshots; an ordinary downloaded run contains its
own current component sources. Run the command inside the preserved container
with its exact digest in `PAPER_RUNTIME_IMAGE` and supply both variant options:

```sh
python3 scripts/check-multi-repository.py \
  --source-lock source-lock.json \
  --reference-root /reference \
  --reference-manifest /reference-manifest.json \
  --code-source-lock /variants/mr04/source-lock.json \
  --failure-source-lock /variants/mr08/source-lock.json \
  --output /outputs/multi-repository \
  --timeout 180
```

A fresh full invocation declares18 attempts. An explicit continuation from the
preserved first FAILED receipt imports only its six completed MR-01–03 attempts
and declares12 remaining actual attempts. Imported outputs and producing records
keep their genuine earlier source/execution pins; they are never recalculated. Apply an outer container wall limit as well as
its cooperative per-attempt limit: synchronous Quarto rendering has its own
finite process timeout. Preserve failed/partial receipts; execution is never
replayed automatically. Record exact source/input/output hashes, the command,
container digest and CPU/memory limits before interpreting the result.

MR-04 changes only the Buffered job expression from
`buffer = context$settings$mse_buffer` to
`buffer = min(context$settings$mse_buffer, 0.6)` at fixed configuration. MR-08 uses a
separate commit that deliberately stops that job. These validation branches do
not change the default component's scientific source. The corrected MR-04 expression selects the supported0.6 fraction at the fixed
0.8 setting. The first attempted expression produced an unsupported0.72 and
failed; its original receipt and source commit remain preserved. The runner
verifies that all other contributing component bytes are unchanged. Without supplied locks,
its optional variant helper needs Git and creates isolated local test commits;
container execution can instead use the parent-precommitted snapshot locks.

MR-05 injects malformed transferred file bytes with explicitly labelled
fixture-only checkpoint checksums. It preserves and restores the real producer
record and output before corrected calls. MR-06 checks missing/tampered files,
MR-07 checks stale producing material, and MR-08 keeps earlier reports identifiable
while testing failure and recovery. None of these injected adverse fixtures is
attributed to an unobserved operational fisheries event.

`evidence.json` records attempted cases, retained producing pins, comparison
results and output hashes. The immutable comparator remains `verify.py` with its
existing metric-specific rules. Downloaded runs include this runner, guide,
component source snapshots and origins, so the actual files can be inspected and
repeated offline when the pinned runtime image is already available. Complete
MR-01–08 repetition also needs the reference and variant companion sources above.
Successful conformance does not approve model adequacy,
management advice, operational adoption or a performance improvement.


For an explicit checkpoint continuation, supply the corrected MR-04 snapshot and a fresh
output directory. Append these explicit checkpoint options to the command above:

```sh
--continue-from /prior/evidence.json \
--continue-sha256 c1e545a9faacc19ea04d13eeab510f3bbb66846b54c47414e461a03752b09f22 \
--checkpoint-origin /prior-source/coordinator-origin.json \
--checkpoint-origin-sha256 bf3a231102e6150b838657e8c67fe031c3704ee0bd7b0483695163d83d7b17cc
```

The preserved coordinator origin must name executable commit
`5cca42bedf3ea61027b282799400adf8483980b9`. The new executable commit is separately
hydrated. All analytical/core source and input hashes must match the original;
only this proof runner, its two software-test files, this guide and the optional
Dockerfile compatibility declaration may differ. Both supplied component variant
locks and the exact monorepo reference manifest remain mandatory. The validator
checks the original FAILED receipt, complete artifact membership/bytes, settings,
producing records, signatures and image before any new case. It copies the six
completed output directories into the new evidence root, rechecks their recorded
bytes and existing-output comparisons, and records explicit import provenance.
The failed first MR-04 remains linked through its immutable prior receipt;
continuation is selected by the parent and never happens automatically.

The public companion supplies the mono reference/manifest, both component
variants and a pinned coordinator closure for a fresh18-attempt repetition.
It excludes checkpoint outputs and administrative execution records. Optional
continuation additionally requires the separately preserved first six output
directories, original FAILED receipt and original coordinator origin. Those raw
checkpoint files belong to a separate recovery archive. Keep each invocation's
raw receipts unchanged. The preserved SPC image has no Git executable; the eight
Git-checkout software fixtures are explicitly skipped there, while two Git-free
inventory/identity checks remain active. Their Git-backed host checks are separate
from the actual snapshot/R evidence and from scientific review.
