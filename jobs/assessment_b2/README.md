# Assessment B2 (`assessment_b2`)

Fit the toy Schaefer model to index B with the selected fixed intrinsic growth and initial biomass equal to K. RTMB estimates one log(K) parameter; catchability q is profiled.

Analyst role: Assessment analyst. The entry point is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Previous jobs: [Prepare inputs B (`prepare_b`)](../prepare_b/README.md)

Input files: Joined index and catch `rows` in `runs/prepare_b/output.json`.

Saved settings: `growth_rate_2` saved as `r` (default: 0.30; choices: 0.25, 0.30, 0.35).

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.
The result records feasibility, biomass recurrence balance, objective gradient and the projected gradient at a parameter bound. Balance uses the supplied catches; it is not an independent catch fit.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=assessment_b2
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

## Outputs and downstream jobs

- `runs/assessment_b2/output.json`: the R calculation result.
- `runs/assessment_b2/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/assessment_b2/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [Compare assessments (`assessment_summary`)](../assessment_summary/README.md), [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_b2/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_b2/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_b2/record.json).
