# Quality check (`qc`)

Check positive effort, non-negative catch and unique observation identifiers. If an invalid effort or catch is found, demonstrate returning the submission and saving corrected source records before checking them again.

Owner: Data curator.

## Inputs and settings

Declared upstream jobs: [Data submission (`submission`)](../submission/README.md)

Incoming artifacts: `runs/submission/output.json`: fishing observations and annual catches. The correction cycle reloads the supplied data and can overwrite the saved submission `output.json`, `report.html` and `record.json`.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from qc --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/qc/output.json`: returned observation IDs, row count and check results.
- `runs/qc/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/qc/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [Prepare and load (`database`)](../database/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/qc/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/qc/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/qc/record.json).
