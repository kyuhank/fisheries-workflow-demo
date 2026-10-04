# CPUE analysis A (`cpue_a`)

Fit a Poisson GLM with year and vessel effects and a log(hooks / 1000) effort offset. Apply the selected effort filter and normalise the reference-vessel index to its first year.

Analyst role: CPUE analyst. The entry point is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [Extract data (`extract`)](../extract/README.md)

Incoming artifacts: The `sets` rows in `runs/extract/output.json`.

Saved settings: `min_hooks_a` saved as `min_hooks` (fresh default: 0). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=cpue_a
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

## Outputs and downstream jobs

- `runs/cpue_a/output.json`: the R calculation result.
- `runs/cpue_a/report.html`: a result page from the shared [renderer](../../workflow/reports.py).
- `runs/cpue_a/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md), [Prepare inputs A (`prepare_a`)](../prepare_a/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/record.json).
