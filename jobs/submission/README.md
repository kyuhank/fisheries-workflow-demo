# Data submission (`submission`)

Assemble the supplied synthetic catch and effort records through the selected final year. The first effort value is deliberately set to zero to demonstrate the correction cycle.

Owner: Data provider.

## Inputs and settings

Declared upstream jobs: None.

Incoming artifacts: [`data/fishery.sqlite`](../../data/fishery.sqlite): `sets` and `removals` tables. [`data/submission.json`](../../data/submission.json) adds the supplied batch only when `last_year` is 2024.

Saved settings: `last_year` is saved as `last_year` (fresh default: 2023). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from submission --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/submission/output.json`: submission observations and annual catches.
- `runs/submission/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/submission/record.json`: run identity, settings, input lineage and artifact checksums.

The full-workflow QC correction replaces these saved submission artifacts with corrected records. The saved example below contains that corrected submission.

These paths are generated run artifacts. Declared downstream jobs: [Quality check (`qc`)](../qc/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/record.json).
