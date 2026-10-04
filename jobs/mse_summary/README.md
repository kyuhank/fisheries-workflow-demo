# MSE results summary (`mse_summary`)

Compare the three rules only when fitted stocks, scenarios and the actual saved error vectors match. Summarise catches, biomass and catch stability.

Owner: MSE analyst. The readable entrypoint is [run.R](run.R), using shared [mse.R](../../workflow/r/mse.R).

## Inputs and settings

Declared upstream jobs: [Constant catch (`mse_constant`)](../mse_constant/README.md), [Index rule (`mse_index`)](../mse_index/README.md), [Buffered rule (`mse_buffered`)](../mse_buffered/README.md)

Incoming artifacts: Completed constant, index and buffered rule outputs, including their actual common error vectors.

Saved settings: No job-specific settings (`{}`). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
python3 run.py --from mse_summary --scope job
```

The coordinator and R run inside the declared R/RTMB/Quarto container; the coordinator refreshes required inputs before calling the job. The run record identifies the actual image and versions. `--output DIR` changes the default `runs` directory; `--settings FILE` supplies JSON setting overrides.

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

## Outputs and downstream jobs

- `runs/mse_summary/output.json`: the R calculation result.
- `runs/mse_summary/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/mse_summary/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [MSE report (`mse_report`)](../mse_report/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/record.json).
