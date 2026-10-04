# Assessment A2 (`assessment_a2`)

Fit the toy Schaefer model to index A with the selected fixed intrinsic growth and initial biomass equal to K. RTMB estimates one log(K) parameter; catchability q is profiled.

Owner: Assessment analyst. The readable entrypoint is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Prepare inputs A (`prepare_a`)](../prepare_a/README.md)

Incoming artifacts: Joined index and catch `rows` in `runs/prepare_a/output.json`.

Saved settings: `growth_rate_2` saved as `r` (fresh default: 0.30; choices: 0.25, 0.30, 0.35). Snapshot lineage is preserved separately; `mse` controls the active graph.

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.
The result records feasibility, biomass recurrence balance, objective gradient and the projected gradient at a parameter bound. Balance uses the supplied catches; it is not an independent catch fit.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=assessment_a2
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/assessment_a2/output.json`: the R calculation result.
- `runs/assessment_a2/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/assessment_a2/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [Compare assessments (`assessment_summary`)](../assessment_summary/README.md), [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a2/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a2/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a2/record.json).
