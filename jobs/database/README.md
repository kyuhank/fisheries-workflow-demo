# Prepare and load (`database`)

Check the accepted records and calculate snapshot coverage in R. The coordinator stores these same records in the SQLite snapshot.

Analyst role: Data curator. The entry point is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Quality check (`qc`)](../qc/README.md)

Incoming artifacts: QC is the declared scheduling gate. The calculation reads accepted `runs/submission/output.json` rows; the QC result is recorded as the declared parent.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=database
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

## Outputs and downstream jobs

- `runs/database/output.json`: the R calculation result.
- `runs/database/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/database/record.json`: inputs, settings, R source hashes, actual container identity and software used.
- `runs/database/snapshot.sqlite`: the accepted database snapshot.

Downstream jobs: [Extract data (`extract`)](../extract/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/database/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/database/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/database/record.json) · [SQLite snapshot](https://kyuhank.github.io/fisheries-workflow-demo/example/database/snapshot.sqlite).
