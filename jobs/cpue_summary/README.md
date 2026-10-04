# Compare CPUE results (`cpue_summary`)

Collect both fitted CPUE series under their declared job titles for comparison in plots and tables.

Owner: CPUE analyst.

## Inputs and settings

Declared upstream jobs: [CPUE analysis A (`cpue_a`)](../cpue_a/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md)

Incoming artifacts: `runs/cpue_a/output.json` and `runs/cpue_b/output.json`: each result's `series`.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from cpue_summary --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/cpue_summary/output.json`: the two named CPUE series.
- `runs/cpue_summary/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/cpue_summary/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [CPUE report (`cpue_report`)](../cpue_report/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/record.json).
