# MSE report (`mse_report`)

Pass the MSE comparison data through unchanged. The shared report renderer presents the tested procedures, trade-offs and limits of this illustrative example.

Owner: MSE analyst.

## Inputs and settings

Declared upstream jobs: [MSE results summary (`mse_summary`)](../mse_summary/README.md)

Incoming artifacts: `runs/mse_summary/output.json`: the comparison result, returned unchanged.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from mse_report --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

MSE must be enabled (`"mse": true`, the fresh-run default) for this job to be selected.

## Outputs and downstream jobs

- `runs/mse_report/output.json`: the unchanged MSE summary.
- `runs/mse_report/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/mse_report/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: None.

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/record.json).
