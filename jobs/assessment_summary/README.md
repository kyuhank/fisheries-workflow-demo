# Compare assessments (`assessment_summary`)

Compare the four fixed-growth Schaefer sensitivity cases, their biomass trajectories and fit diagnostics.

Owner: Assessment analyst. The readable entrypoint is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md), [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md)

Incoming artifacts: The fitted `series`, r, K, convergence and bounds in all four assessment outputs.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=assessment_summary
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/assessment_summary/output.json`: the R calculation result.
- `runs/assessment_summary/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/assessment_summary/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [Assessment report (`assessment_report`)](../assessment_report/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/record.json).
