# Compare assessments (`assessment_summary`)

Collect the four assessment series and their mortality, boundary-fit and catch-check diagnostics for comparison.

Owner: Assessment analyst.

## Inputs and settings

Declared upstream jobs: [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md), [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md)

Incoming artifacts: `runs/assessment_a1/output.json`, `runs/assessment_a2/output.json`, `runs/assessment_b1/output.json` and `runs/assessment_b2/output.json`: fitted `series` and diagnostics.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from assessment_summary --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/assessment_summary/output.json`: the four named series and diagnostics.
- `runs/assessment_summary/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/assessment_summary/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [Assessment report (`assessment_report`)](../assessment_report/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/record.json).
