# Prepare inputs A (`prepare_a`)

Join CPUE index A to annual catches by year and reject an index year without a matching catch.

Analyst role: Assessment analyst. The entry point is [run.R](run.R), using shared [common.R](../../workflow/r/common.R).

## Inputs and settings

Previous jobs: [Extract data (`extract`)](../extract/README.md), [CPUE analysis A (`cpue_a`)](../cpue_a/README.md)

Input files: The index `series` in `runs/cpue_a/output.json` and annual `catch` in `runs/extract/output.json`.

Saved settings: No job-specific settings (`{}`).

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=prepare_a
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

## Outputs and downstream jobs

- `runs/prepare_a/output.json`: the R calculation result.
- `runs/prepare_a/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/prepare_a/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/record.json).
