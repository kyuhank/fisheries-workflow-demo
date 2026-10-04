# MSE report (`mse_report`)

Pass the saved management-trial comparison to the concise Quarto report. Trial fractions describe this conditional illustration; they are not validated risk estimates.

Owner: MSE analyst. The readable entrypoint is [run.R](run.R), using shared [mse.R](../../workflow/r/mse.R).

## Inputs and settings

Declared upstream jobs: [MSE results summary (`mse_summary`)](../mse_summary/README.md)

Incoming artifacts: `runs/mse_summary/output.json` and the report job's saved run record.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=mse_report
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

## Outputs and downstream jobs

- `runs/mse_report/output.json`: the R calculation result.
- `runs/mse_report/report.html`: the native Quarto output from [report.qmd](report.qmd).
- `runs/mse_report/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: None.

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/record.json).
