# Compare CPUE results (`cpue_summary`)

Collect the two fitted CPUE series for comparison without fitting another model.

Owner: CPUE analyst. The readable entrypoint is [run.R](run.R), using shared [models.R](../../workflow/r/models.R).

## Inputs and settings

Declared upstream jobs: [CPUE analysis A (`cpue_a`)](../cpue_a/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md)

Incoming artifacts: The `series` in `runs/cpue_a/output.json` and `runs/cpue_b/output.json`.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=cpue_summary
```

The coordinator refreshes required inputs and calls the job through `workflow/Makefile`. The run record identifies the actual image and versions. `OUTPUT=DIR` changes the default `runs` directory; `SETTINGS=FILE` supplies JSON settings.

## Outputs and downstream jobs

- `runs/cpue_summary/output.json`: the R calculation result.
- `runs/cpue_summary/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/cpue_summary/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [CPUE report (`cpue_report`)](../cpue_report/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/record.json).
