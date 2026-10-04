# Prepare and load (`database`)

Check the accepted records and calculate snapshot coverage in R. The coordinator stores these same records in the SQLite snapshot.

Owner: Data curator. The readable entrypoint is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Quality check (`qc`)](../qc/README.md)

Incoming artifacts: QC is the declared scheduling gate. The calculation reads accepted `runs/submission/output.json` rows; the QC result is recorded as the declared parent.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
python3 run.py --from database --scope job
```

The coordinator and R run inside the declared R/RTMB/Quarto container; the coordinator refreshes required inputs before calling the job. The run record identifies the actual image and versions. `--output DIR` changes the default `runs` directory; `--settings FILE` supplies JSON setting overrides.

## Outputs and downstream jobs

- `runs/database/output.json`: the R calculation result.
- `runs/database/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/database/record.json`: inputs, settings, R source hashes, actual container identity and software used.
- `runs/database/snapshot.sqlite`: the accepted database snapshot.

These are generated run artifacts. Declared downstream jobs: [Extract data (`extract`)](../extract/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/database/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/database/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/database/record.json) · [SQLite snapshot](https://kyuhank.github.io/fisheries-workflow-demo/example/database/snapshot.sqlite).
