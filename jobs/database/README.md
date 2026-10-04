# Prepare and load (`database`)

Load accepted synthetic records into a fixed SQLite snapshot and summarise its coverage and composition.

Owner: Data curator.

## Inputs and settings

Declared upstream jobs: [Quality check (`qc`)](../qc/README.md)

Incoming artifacts: QC is the declared scheduling gate and recorded parent. The calculation reads accepted records from `runs/submission/output.json`; it does not consume `qc/output.json`.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from database --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/database/output.json`: snapshot coverage and composition.
- `runs/database/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/database/record.json`: run identity, settings, input lineage and artifact checksums.
- `runs/database/snapshot.sqlite`: the accepted database snapshot.

These paths are generated run artifacts. Declared downstream jobs: [Extract data (`extract`)](../extract/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/database/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/database/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/database/record.json) · [SQLite snapshot](https://kyuhank.github.io/fisheries-workflow-demo/example/database/snapshot.sqlite).
