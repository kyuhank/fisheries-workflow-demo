# MSE results summary (`mse_summary`)

Compare the three rules only when fitted stocks, scenarios and the actual saved error vectors match. Summarise catches, biomass and catch stability.

Analyst role: MSE analyst. The entry point is [run.R](run.R), using shared [mse.R](../../workflow/r/mse.R).

## Inputs and settings

Previous jobs: [Constant catch (`mse_constant`)](../mse_constant/README.md), [Index rule (`mse_index`)](../mse_index/README.md), [Buffered rule (`mse_buffered`)](../mse_buffered/README.md)

Input files: Completed constant, index and buffered rule outputs, including their actual common error vectors.

Saved settings: No job-specific settings (`{}`).

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=mse_summary
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

## Outputs and downstream jobs

- `runs/mse_summary/output.json`: the R calculation result.
- `runs/mse_summary/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/mse_summary/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [MSE report (`mse_report`)](../mse_report/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/record.json).
