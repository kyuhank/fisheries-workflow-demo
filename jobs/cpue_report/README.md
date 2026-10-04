# CPUE report (`cpue_report`)

Pass the CPUE comparison data through unchanged. The shared report renderer writes the account of methods and results.

Owner: CPUE analyst.

## Inputs and settings

Declared upstream jobs: [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md)

Incoming artifacts: `runs/cpue_summary/output.json`: the comparison result, returned unchanged.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from cpue_report --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/cpue_report/output.json`: the unchanged CPUE summary.
- `runs/cpue_report/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/cpue_report/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: None.

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/record.json).
