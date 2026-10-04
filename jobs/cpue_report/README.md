# CPUE report (`cpue_report`)

Pass the saved CPUE comparison to the concise Quarto report. The report reads the result and run record without refitting the GLMs.

Owner: CPUE analyst. The readable entrypoint is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md)

Incoming artifacts: `runs/cpue_summary/output.json` and the report job's saved run record.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=cpue_report
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/cpue_report/output.json`: the R calculation result.
- `runs/cpue_report/report.html`: the native Quarto output from [report.qmd](report.qmd).
- `runs/cpue_report/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: None.

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/record.json).
