# Prepare and load (`database`)

Check the accepted records and calculate snapshot coverage in R. The coordinator stores these same records in the SQLite snapshot.

**Path:** Accepted rows → save SQLite snapshot → fixed data inputs.

**Inputs:** QC is the declared scheduling gate. The calculation reads accepted `runs/submission/output.json` rows; the QC result is recorded as the declared parent.

**From:** [Quality check (`qc`)](../qc/README.md).

**Settings:** No job-specific settings (`{}`).

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=database
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/database/output.json` | saved calculation result |
| `runs/database/report.html` | result page from [shared renderer](../../workflow/reports.py) |
| `runs/database/record.json` | producing inputs, settings, exact code and software |
| `runs/database/snapshot.sqlite` | accepted fixed database snapshot |

**Used by:** [Extract data (`extract`)](../extract/README.md).

[Saved report](https://kyuhank.github.io/fisheries-workflow-demo/example/database/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/database/record.json)
