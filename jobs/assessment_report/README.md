# Assessment report (`assessment_report`)

Pass the saved assessment comparison to the concise Quarto report. The report describes the fixed assumptions, convergence and bounds without refitting or claiming confidence intervals.

Owner: Assessment analyst. The readable entrypoint is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Compare assessments (`assessment_summary`)](../assessment_summary/README.md)

Incoming artifacts: `runs/assessment_summary/output.json` and the report job's saved run record.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.

## Run in the container

Inside the declared container, from the repository root:

```sh
python3 run.py --from assessment_report --scope job
```

The coordinator and R run inside the declared R/RTMB/Quarto container; the coordinator refreshes required inputs before calling the job. The run record identifies the actual image and versions. `--output DIR` changes the default `runs` directory; `--settings FILE` supplies JSON setting overrides.

## Outputs and downstream jobs

- `runs/assessment_report/output.json`: the R calculation result.
- `runs/assessment_report/report.html`: the native Quarto output from [report.qmd](report.qmd).
- `runs/assessment_report/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: None.

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/record.json).
