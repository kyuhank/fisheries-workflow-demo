# CPUE analysis B (`cpue_b`)

Fit the alternative Poisson GLM with year effects and the same effort offset. Retain valid observations and normalise the index to its first year.

Owner: CPUE analyst. The readable entrypoint is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Extract data (`extract`)](../extract/README.md)

Incoming artifacts: The `sets` rows in `runs/extract/output.json`.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=cpue_b
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/cpue_b/output.json`: the R calculation result.
- `runs/cpue_b/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/cpue_b/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md), [Prepare inputs B (`prepare_b`)](../prepare_b/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_b/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_b/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_b/record.json).
