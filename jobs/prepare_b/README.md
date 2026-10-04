# Prepare inputs B (`prepare_b`)

Join CPUE index B to annual catches by year and reject an index year without a matching catch.

Owner: Assessment analyst.

## Inputs and settings

Declared upstream jobs: [Extract data (`extract`)](../extract/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md)

Incoming artifacts: `runs/cpue_b/output.json`: the index `series`; `runs/extract/output.json`: annual `catch` records.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from prepare_b --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/prepare_b/output.json`: index B and catch rows joined by year.
- `runs/prepare_b/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/prepare_b/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/record.json).
