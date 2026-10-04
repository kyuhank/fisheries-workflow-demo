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
python3 run.py --from cpue_summary --scope job
```

The coordinator and R run inside the declared R/RTMB/Quarto container; the coordinator refreshes required inputs before calling the job. The run record identifies the actual image and versions. `--output DIR` changes the default `runs` directory; `--settings FILE` supplies JSON setting overrides.

## Outputs and downstream jobs

- `runs/cpue_summary/output.json`: the R calculation result.
- `runs/cpue_summary/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/cpue_summary/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [CPUE report (`cpue_report`)](../cpue_report/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/record.json).
