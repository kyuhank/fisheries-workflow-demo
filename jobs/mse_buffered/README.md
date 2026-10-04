# Buffered rule (`mse_buffered`)

Test index-based catch steps with the selected buffer and a 15% annual advice-change limit in the common seeded Schaefer management trials.

Owner: MSE analyst. The readable entrypoint is [run.R](run.R), using shared [mse.R](../../workflow/r/mse.R).

## Inputs and settings

Declared upstream jobs: [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md)

Incoming artifacts: Stocks, scenarios and saved `error_streams` in `runs/mse_prepare/output.json`.

Saved settings: `mse_buffer` saved as `buffer` (fresh default: 0.8). Snapshot lineage is preserved separately; `mse` controls the active graph.

## Run in the container

Inside the declared container, from the repository root:

```sh
python3 run.py --from mse_buffered --scope job
```

The coordinator and R run inside the declared R/RTMB/Quarto container; the coordinator refreshes required inputs before calling the job. The run record identifies the actual image and versions. `--output DIR` changes the default `runs` directory; `--settings FILE` supplies JSON setting overrides.

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

## Outputs and downstream jobs

- `runs/mse_buffered/output.json`: the R calculation result.
- `runs/mse_buffered/report.html`: a readable result page from the shared [renderer](../../workflow/reports.py).
- `runs/mse_buffered/record.json`: inputs, settings, R source hashes, actual container identity and software used.

These are generated run artifacts. Declared downstream jobs: [MSE results summary (`mse_summary`)](../mse_summary/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_buffered/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_buffered/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_buffered/record.json).
