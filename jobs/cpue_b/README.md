# CPUE analysis B (`cpue_b`)

Fit the illustrative CPUE index with year effects only and no minimum-effort filter. Normalise the index to its first year.

Owner: CPUE analyst.

## Inputs and settings

Declared upstream jobs: [Extract data (`extract`)](../extract/README.md)

Incoming artifacts: `runs/extract/output.json`: the `sets` observations.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from cpue_b --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/cpue_b/output.json`: the CPUE series, observation counts and fit diagnostics.
- `runs/cpue_b/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/cpue_b/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md), [Prepare inputs B (`prepare_b`)](../prepare_b/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_b/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_b/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_b/record.json).
