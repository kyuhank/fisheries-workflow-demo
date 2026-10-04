# Quality check (`qc`)

Check positive effort, non-negative catch and unique observation IDs in R. When correction is needed, return corrected raw-source rows for the coordinator to save as a replacement submission.

Analyst role: Data curator. The entry point is [run.R](run.R), using shared [common.R](../../workflow/r/common.R).

## Inputs and settings

Declared upstream jobs: [Data submission (`submission`)](../submission/README.md)

Incoming artifacts: `runs/submission/output.json` and the raw supplied source rows. Correction can replace the submission `output.json`, `report.html` and `record.json`.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=qc
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

## Outputs and downstream jobs

- `runs/qc/output.json`: the R calculation result.
- `runs/qc/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/qc/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [Prepare and load (`database`)](../database/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/qc/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/qc/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/qc/record.json).
