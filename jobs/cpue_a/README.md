# CPUE analysis A (`cpue_a`)

Estimate annual CPUE with a quasipoisson GLM adjusting for year and cell–quarter stratum.

**Path:** Catch and effort rows → adjusted GLM → annual CPUE index A.

**Inputs:** The aggregate `sets` rows in `runs/extract/output.json`.

**From:** [Extract data (`extract`)](../extract/README.md).

**Settings:** `min_hooks_a`, recorded as `min_hooks` (default: 0).

Use a log(hooks / 1000) offset. Predict each supported stratum at 1,000 hooks and average on the response scale with equal fixed weights; divide by the first-year mean. The existing 1,200-hook filter excludes no public rows and is hidden in the public-data app. Synthetic fixtures retain the vessel-effect Poisson example.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=cpue_a
```

[run.R](https://github.com/kyuhank/fisheries-workflow-cpue-demo/blob/7d17fc5962466cdabc27d17e004bed87136b38bc/jobs/cpue_a/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/cpue_a/output.json` | annual indices, absolute CPUE, prediction support and model checks |
| `runs/cpue_a/report.pdf` | compiled Quarto result PDF |
| `runs/cpue_a/report.html` | result page from [component renderer](https://github.com/kyuhank/fisheries-workflow-cpue-demo/blob/7d17fc5962466cdabc27d17e004bed87136b38bc/R/render.R) |
| `runs/cpue_a/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md), [Prepare inputs A (`prepare_a`)](../prepare_a/README.md).

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_a/record.json)
