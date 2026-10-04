# Prepare MSE (`mse_prepare`)

Reconstruct the first future-year stock states from all four fitted assessments and retain the common simulation assumptions, rules and limitations for the illustrative MSE.

Owner: MSE analyst.

## Inputs and settings

Declared upstream jobs: [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md), [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md)

Incoming artifacts: `runs/assessment_a1/output.json`, `runs/assessment_a2/output.json`, `runs/assessment_b1/output.json` and `runs/assessment_b2/output.json`: fitted parameters, annual catches and observed indices.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from mse_prepare --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

MSE must be enabled (`"mse": true`, the fresh-run default) for this job to be selected.

## Outputs and downstream jobs

- `runs/mse_prepare/output.json`: operating models, assumptions, rules and limitations.
- `runs/mse_prepare/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/mse_prepare/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [Constant catch (`mse_constant`)](../mse_constant/README.md), [Index rule (`mse_index`)](../mse_index/README.md), [Buffered rule (`mse_buffered`)](../mse_buffered/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_prepare/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_prepare/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_prepare/record.json).
