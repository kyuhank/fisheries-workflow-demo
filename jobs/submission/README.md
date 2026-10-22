# Data submission (`submission`)

Select the requested years from the supplied public catch and effort records.

**Path:** Source records → select final year → submitted rows.

**Inputs:** [`data/public-source.json`](../../data/public-source.json), including aggregate fishing rows and the separate annual catch series.

**From:** None.

**Settings:** `last_year` (default: 2021).

The public input preserves released values. The invalid-effort correction cycle is retained only for synthetic fixtures.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=submission
```

[run.R](https://github.com/kyuhank/fisheries-workflow-cpue-demo/blob/7d17fc5962466cdabc27d17e004bed87136b38bc/jobs/submission/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/submission/output.json` | saved calculation result |
| `runs/submission/report.pdf` | compiled Quarto result PDF |
| `runs/submission/report.html` | result page from [component renderer](https://github.com/kyuhank/fisheries-workflow-cpue-demo/blob/7d17fc5962466cdabc27d17e004bed87136b38bc/R/render.R) |
| `runs/submission/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Quality check (`qc`)](../qc/README.md).

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/submission/record.json)
