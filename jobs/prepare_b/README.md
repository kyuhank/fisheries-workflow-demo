# Prepare inputs B (`prepare_b`)

Join CPUE index B to annual catches by year and reject an index year without a matching catch.

Owner: Assessment analyst. The readable entrypoint is [run.R](run.R), using shared [common.R](../../workflow/r/common.R).

## Inputs and settings

Declared upstream jobs: [Extract data (`extract`)](../extract/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md)

Incoming artifacts: The index `series` in `runs/cpue_b/output.json` and annual `catch` in `runs/extract/output.json`.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=prepare_b
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/prepare_b/output.json`: the R calculation result.
- `runs/prepare_b/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/prepare_b/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/record.json).
