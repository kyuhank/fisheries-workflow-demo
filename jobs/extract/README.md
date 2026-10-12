# Extract data (`extract`)

Use recorded SQLite queries to select the fixed CPUE support and annual catches.

**Path:** SQLite snapshot → recorded SQL → CPUE rows and annual catches.

**Inputs:** `runs/database/snapshot.sqlite`, [`extract.sql`](../../workflow/extract.sql) and [`extract-catch.sql`](../../workflow/extract-catch.sql).

**From:** [Prepare and load (`database`)](../database/README.md).

**Settings:** No job-specific settings (`{}`).

CPUE rows retain fleet, year, cell, quarter, hooks and albacore catch in numbers. Annual catch is a separate tonnes series. Released zero counts are retained; absent or suppressed values are not converted to zeros.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=extract
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/extract/output.json` | saved calculation result |
| `runs/extract/report.html` | result page from [shared renderer](../../workflow/reports.py) |
| `runs/extract/record.json` | producing inputs, settings, exact code and software |

**Used by:** [CPUE analysis A (`cpue_a`)](../cpue_a/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md), [Prepare inputs A (`prepare_a`)](../prepare_a/README.md), [Prepare inputs B (`prepare_b`)](../prepare_b/README.md).

[Saved report](https://kyuhank.github.io/fisheries-workflow-demo/example/extract/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/extract/record.json)
