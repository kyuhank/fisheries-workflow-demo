# Assessment report (`assessment_report`)

Pass the assessment comparison data through unchanged. The shared report renderer writes the analytical report.

Owner: Assessment analyst.

## Inputs and settings

Declared upstream jobs: [Compare assessments (`assessment_summary`)](../assessment_summary/README.md)

Incoming artifacts: `runs/assessment_summary/output.json`: the comparison result, returned unchanged.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from assessment_report --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/assessment_report/output.json`: the unchanged assessment summary.
- `runs/assessment_report/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/assessment_report/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: None.

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/record.json).
