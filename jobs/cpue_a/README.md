# CPUE analysis A (`cpue_a`)

Fit the illustrative CPUE index with year and vessel effects, after applying the selected minimum-effort filter. Normalise the index to its first year.

Owner: CPUE analyst.

## Inputs and settings

Declared upstream jobs: [Extract data (`extract`)](../extract/README.md)

Incoming artifacts: `runs/extract/output.json`: the `sets` observations.

Saved settings: `min_hooks_a` is saved as `min_hooks` (fresh default: 0). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from cpue_a --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/cpue_a/output.json`: the CPUE series, observation counts and fit diagnostics.
- `runs/cpue_a/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/cpue_a/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md), [Prepare inputs A (`prepare_a`)](../prepare_a/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/record.json).
