# Prepare MSE (`mse_prepare`)

Reconstruct next-year Schaefer stocks after the terminal assessment catch, then prepare common seeded growth and observation errors once for all three management rules.

Analyst role: MSE analyst. The entry point is [run.R](run.R), using shared [mse.R](../../workflow/r/mse.R).

## Inputs and settings

Declared upstream jobs: [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md), [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md)

Incoming artifacts: All four assessment outputs: r, K, q, annual catches, observed indices and the declared next-year biomass.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=mse_prepare
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

## Outputs and downstream jobs

- `runs/mse_prepare/output.json`: the R calculation result.
- `runs/mse_prepare/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/mse_prepare/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [Constant catch (`mse_constant`)](../mse_constant/README.md), [Index rule (`mse_index`)](../mse_index/README.md), [Buffered rule (`mse_buffered`)](../mse_buffered/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_prepare/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_prepare/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_prepare/record.json).
