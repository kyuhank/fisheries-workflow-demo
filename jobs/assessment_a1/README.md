# Assessment A1 (`assessment_a1`)

Fit the toy Schaefer model to index A with fixed intrinsic growth r = 0.25 and initial biomass equal to K. RTMB estimates one log(K) parameter; catchability q is profiled.

Owner: Assessment analyst. The readable entrypoint is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Prepare inputs A (`prepare_a`)](../prepare_a/README.md)

Incoming artifacts: Joined index and catch `rows` in `runs/prepare_a/output.json`.

Saved settings: Fixed `r = 0.25`. Snapshot lineage is preserved separately; `mse` controls the active graph.

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.
The result records feasibility, biomass recurrence balance, objective gradient and the projected gradient at a parameter bound. Balance uses the supplied catches; it is not an independent catch fit.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=assessment_a1
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/assessment_a1/output.json`: the R calculation result.
- `runs/assessment_a1/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/assessment_a1/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [Compare assessments (`assessment_summary`)](../assessment_summary/README.md), [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a1/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a1/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a1/record.json).
