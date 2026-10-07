# Constant catch (`mse_constant`)

Test fixed advice equal to recent mean catch in the common seeded Schaefer management trials.

Analyst role: MSE analyst. The entry point is [run.R](run.R), using shared [mse.R](../../workflow/r/mse.R).

## Inputs and settings

Previous jobs: [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md)

Input files: Stocks, scenarios and saved `error_streams` in `runs/mse_prepare/output.json`.

Saved settings: No job-specific settings (`{}`).

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=mse_constant
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

## Outputs and downstream jobs

- `runs/mse_constant/output.json`: the R calculation result.
- `runs/mse_constant/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/mse_constant/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [MSE results summary (`mse_summary`)](../mse_summary/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_constant/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_constant/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_constant/record.json).
