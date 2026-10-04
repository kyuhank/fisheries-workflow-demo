# Extract data (`extract`)

Run the saved SQL against the database snapshot to select valid fishing observations and annual removals, retaining zero catches and vessel identity.

Owner: Data analyst.

## Inputs and settings

Declared upstream jobs: [Prepare and load (`database`)](../database/README.md)

Incoming artifacts: `runs/database/snapshot.sqlite`, plus [`workflow/extract.sql`](../../workflow/extract.sql) and [`workflow/extract-catch.sql`](../../workflow/extract-catch.sql). The calculation reads the SQLite snapshot rather than the database summary JSON.

Saved settings: No job-specific settings are saved (`record.json.settings` is `{}`). Every job also preserves snapshot lineage separately; `mse` controls which jobs are in the active graph.

## Run

From the repository root:

```sh
python3 run.py --from extract --scope job
```

This selects the job and refreshes required upstream inputs when needed. `--output DIR` replaces the default `runs` directory; `--settings FILE` overrides current settings with values from a JSON file.

## Outputs and downstream jobs

- `runs/extract/output.json`: selected observations, annual catches and the SQL used.
- `runs/extract/report.html`: the page produced by the shared [report renderer](../../workflow/reports.py).
- `runs/extract/record.json`: run identity, settings, input lineage and artifact checksums.

These paths are generated run artifacts. Declared downstream jobs: [CPUE analysis A (`cpue_a`)](../cpue_a/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md), [Prepare inputs A (`prepare_a`)](../prepare_a/README.md), [Prepare inputs B (`prepare_b`)](../prepare_b/README.md)

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/extract/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/extract/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/extract/record.json).
