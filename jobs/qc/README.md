# Quality check (`qc`)

Check positive effort, non-negative released catch and unique source-row IDs.

**Path:** Submitted rows → check effort, catch and IDs → accepted rows.

**Inputs:** `runs/submission/output.json`; supplied raw-source rows are available for correction.

**From:** [Data submission (`submission`)](../submission/README.md).

**Settings:** No job-specific settings (`{}`).

A correction replaces the submitted result and producing record. The public example does not insert an artificial error.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=qc
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/qc/output.json` | saved calculation result |
| `runs/qc/report.html` | result page from [shared renderer](../../workflow/reports.py) |
| `runs/qc/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Prepare and load (`database`)](../database/README.md).

[Saved report](https://kyuhank.github.io/fisheries-workflow-demo/example/qc/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/qc/record.json)
