# Extract data (`extract`)

Check and return observations and annual removals obtained through the real SQLite snapshot queries. Zero catches and vessel identity are retained.

Owner: Data analyst. The readable entrypoint is [run.R](run.R), using shared [common.R](../../workflow/r/common.R).

## Inputs and settings

Declared upstream jobs: [Prepare and load (`database`)](../database/README.md)

Incoming artifacts: `runs/database/snapshot.sqlite` queried using [`extract.sql`](../../workflow/extract.sql) and [`extract-catch.sql`](../../workflow/extract-catch.sql). The adapter supplies the actual query rows and SQL to R.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=extract
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/extract/output.json`: the R calculation result.
- `runs/extract/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/extract/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [CPUE analysis A (`cpue_a`)](../cpue_a/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md), [Prepare inputs A (`prepare_a`)](../prepare_a/README.md), [Prepare inputs B (`prepare_b`)](../prepare_b/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/extract/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/extract/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/extract/record.json).
