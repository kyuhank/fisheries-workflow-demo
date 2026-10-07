# Data submission (`submission`)

Assemble the supplied synthetic catch and effort records in R through the selected final year. Set the first effort value to zero to demonstrate the correction cycle.

Analyst role: Data provider. The entry point is [run.R](run.R), using shared [common.R](../../workflow/r/common.R).

## Inputs and settings

Previous jobs: None.

Input files: [`data/fishery.sqlite`](../../data/fishery.sqlite): base `sets` and `removals`; [`data/submission.json`](../../data/submission.json): the additional 2024 batch. R selects and assembles the requested snapshot.

Saved settings: `last_year` (default: 2023).

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=submission
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

## Outputs and downstream jobs

- `runs/submission/output.json`: the R calculation result.
- `runs/submission/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/submission/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [Quality check (`qc`)](../qc/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/record.json).
