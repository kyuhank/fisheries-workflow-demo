# CPUE analysis B (`cpue_b`)

Estimate the alternative annual CPUE index with a year-and-quarter quasipoisson GLM.

**Path:** Catch and effort rows → year-and-quarter GLM → annual CPUE index B.

**Inputs:** The aggregate `sets` rows in `runs/extract/output.json`.

**From:** [Extract data (`extract`)](../extract/README.md).

**Settings:** No job-specific settings (`{}`).

Use the same log(hooks / 1000) offset, prediction support and first-year normalisation as A, with quarter effects instead of cell–quarter effects. Quarter effects partly confound spatial differences on this support. Saved output includes nominal and standardised fish per 1,000 hooks. Synthetic fixtures retain the year-only Poisson example.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=cpue_b
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/cpue_b/output.json` | annual indices, absolute CPUE, prediction support and model checks |
| `runs/cpue_b/report.html` | result page from [shared renderer](../../workflow/reports.py) |
| `runs/cpue_b/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md), [Prepare inputs B (`prepare_b`)](../prepare_b/README.md).

[Saved report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_b/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_b/record.json)
