# MSE results summary (`mse_summary`)

Combine the three completed management-rule results and check that operating models, scenarios and random trials match before comparing catch, stock levels and catch stability.

Owner: MSE analyst.

## Inputs and settings

Declared upstream jobs: [Constant catch (`mse_constant`)](../mse_constant/README.md), [Index rule (`mse_index`)](../mse_index/README.md), [Buffered rule (`mse_buffered`)](../mse_buffered/README.md)

Incoming artifacts: `runs/mse_constant/output.json`, `runs/mse_index/output.json` and `runs/mse_buffered/output.json`: completed rule simulations and trial identities.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from mse_summary --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

MSE must be enabled (`"mse": true`, the fresh-run default) for this job to be selected.

## Outputs and downstream jobs

- `runs/mse_summary/output.json`: comparison series, metrics, rule settings and trial examples.
- `runs/mse_summary/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/mse_summary/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [MSE report (`mse_report`)](../mse_report/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/record.json).
