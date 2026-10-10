# Repeat the bounded repository checks

The default coordinator selects the exact commits in `source-lock.template.json`.
`python3 scripts/hydrate-sources.py` verifies Git pins and assembles their source
bytes before the network-disabled calculation container starts. Local validation
can use `--local-root ../component-repositories`; the coordinator must be clean
at its actual committed executable revision. `coordinator-origin.json` binds that
revision to the archived coordinator source bytes. This is separate from a later
commit delivering generated site files.

Run `python3 scripts/check-multi-repository.py --plan` to inspect the finite
MR-01–08 inventory without calculations. Numerical execution requires the same
preserved SPC image and a fresh output directory. The parent supplies a pinned
monorepo reference and separately hydrated validation source locks:

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

The runner declares 18 attempts. Apply an outer container wall limit as well as
its cooperative per-attempt limit: synchronous Quarto rendering has its own
finite process timeout. Preserve failed/partial receipts; execution is never
replayed automatically. Record exact source/input/output hashes, the command,
container digest and CPU/memory limits before interpreting the result.

MR-04 changes only the Buffered job expression from
`buffer = context$settings$mse_buffer` to
`buffer = 0.9 * context$settings$mse_buffer` at fixed configuration. MR-08 uses a
separate commit that deliberately stops that job. These validation branches do
not change the default component's scientific source. The runner verifies that
all other contributing component bytes are unchanged. Without supplied locks,
its optional variant helper needs Git and creates isolated local test commits;
container execution can instead use the parent-precommitted snapshot locks.

MR-05 injects malformed transferred file bytes with explicitly labelled
fixture-only checkpoint checksums. It preserves and restores the real producer
record and output before corrected calls. MR-06 checks missing/tampered files,
MR-07 checks stale producing material, and MR-08 keeps earlier reports identifiable
while testing failure and recovery. None of these injected adverse fixtures is
attributed to an unobserved operational fisheries event.

`verification.json` records attempted cases, retained producing pins, comparison
results and output hashes. The immutable comparator remains `verify.py` with its
existing metric-specific rules. Downloaded runs include this runner, guide,
component source snapshots and origins, so the actual files can be inspected and
repeated offline. Successful conformance does not approve model adequacy,
management advice, operational adoption or a performance improvement.
