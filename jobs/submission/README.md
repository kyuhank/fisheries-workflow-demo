# Data submission (`submission`)

Assemble the supplied synthetic catch and effort records in R through the selected final year. Set the first effort value to zero to demonstrate the correction cycle.

Owner: Data provider. The readable entrypoint is [run.R](run.R), using shared [common.R](../../workflow/r/common.R).

## Inputs and settings

Declared upstream jobs: None.

Incoming artifacts: [`data/fishery.sqlite`](../../data/fishery.sqlite): base `sets` and `removals`; [`data/submission.json`](../../data/submission.json): the additional 2024 batch. R selects and assembles the requested snapshot.

Saved settings: `last_year` (fresh default: 2023). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
python3 run.py --from submission --scope job
```

The coordinator and R run inside the declared R/RTMB/Quarto container; the coordinator refreshes required inputs before calling the job. The run record identifies the actual image and versions. `--output DIR` changes the default `runs` directory; `--settings FILE` supplies JSON setting overrides.

## Outputs and downstream jobs

- `runs/submission/output.json`: the R calculation result.
- `runs/submission/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/submission/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [Quality check (`qc`)](../qc/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/record.json).
