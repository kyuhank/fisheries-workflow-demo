# Assessment B1 (`assessment_b1`)

Fit the illustrative age-structured assessment to index B and annual catches with mortality setting 1. Preserve the fitted series and catch-reproduction diagnostics.

Owner: Assessment analyst.

## Inputs and settings

Declared upstream jobs: [Prepare inputs B (`prepare_b`)](../prepare_b/README.md)

Incoming artifacts: `runs/prepare_b/output.json`: joined index and catch `rows`.

Saved settings: Fixed natural mortality 0.20 is saved as `M`. Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from assessment_b1 --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/assessment_b1/output.json`: the fitted series, parameters and diagnostics.
- `runs/assessment_b1/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/assessment_b1/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [Compare assessments (`assessment_summary`)](../assessment_summary/README.md), [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_b1/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_b1/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_b1/record.json).
