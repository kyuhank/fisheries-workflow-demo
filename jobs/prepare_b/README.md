# Prepare inputs B (`prepare_b`)

Join CPUE index B to annual catches by year and reject an index year without a matching catch.

Analyst role: Assessment analyst. The entry point is [run.R](run.R), using shared [common.R](../../workflow/r/common.R).

## Inputs and settings

Previous jobs: [Extract data (`extract`)](../extract/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md)

Input files: The index `series` in `runs/cpue_b/output.json` and annual `catch` in `runs/extract/output.json`.

Saved settings: No job-specific settings (`{}`).

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=prepare_b
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

## Outputs and downstream jobs

- `runs/prepare_b/output.json`: the R calculation result.
- `runs/prepare_b/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/prepare_b/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/record.json).
