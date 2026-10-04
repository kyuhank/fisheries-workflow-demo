# Index rule (`mse_index`)

Test annual catch advice proportional to the three-year mean observed abundance index under the common future conditions prepared for the illustrative MSE.

Owner: MSE analyst.

## Inputs and settings

Declared upstream jobs: [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md)

Incoming artifacts: `runs/mse_prepare/output.json`: operating models, common assumptions, rules and limitations.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from mse_index --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

MSE must be enabled (`"mse": true`, the fresh-run default) for this job to be selected.

## Outputs and downstream jobs

- `runs/mse_index/output.json`: rule settings, annual series, trial metrics and a saved example trial.
- `runs/mse_index/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/mse_index/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [MSE results summary (`mse_summary`)](../mse_summary/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_index/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_index/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_index/record.json).
