# Prepare inputs A (`prepare_a`)

Join CPUE index A to annual catches by year and reject an index year without a matching catch.

Owner: Assessment analyst. The readable entrypoint is [run.R](run.R), using shared [common.R](../../workflow/r/common.R).

## Inputs and settings

Declared upstream jobs: [Extract data (`extract`)](../extract/README.md), [CPUE analysis A (`cpue_a`)](../cpue_a/README.md)

Incoming artifacts: The index `series` in `runs/cpue_a/output.json` and annual `catch` in `runs/extract/output.json`.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=prepare_a
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/prepare_a/output.json`: the R calculation result.
- `runs/prepare_a/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/prepare_a/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/record.json).
