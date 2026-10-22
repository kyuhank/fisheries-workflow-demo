# MSE report (`mse_report`)

Render the saved management-trial comparison as a Quarto report. Trial fractions describe this conditional illustration; they are not validated risk estimates.

**Path:** Saved management comparison → describe trade-offs and limits → MSE report.

**Inputs:** `runs/mse_summary/output.json` and the report job's saved run record.

**From:** [MSE results summary (`mse_summary`)](../mse_summary/README.md).

**Settings:** No job-specific settings (`{}`).

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=mse_report
```

[run.R](https://github.com/kyuhank/fisheries-workflow-mse-demo/blob/bfd7066a5b7fad6bc302bf311d63b20e32dfa9a4/jobs/mse_report/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/mse_report/output.json` | saved calculation result |
| `runs/mse_report/report.pdf` | compiled Quarto result PDF |
| `runs/mse_report/report.html` | result page from [report.qmd](https://github.com/kyuhank/fisheries-workflow-mse-demo/blob/bfd7066a5b7fad6bc302bf311d63b20e32dfa9a4/jobs/mse_report/report.qmd) |
| `runs/mse_report/record.json` | producing inputs, settings, exact code and software |

**Used by:** None.

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/record.json)
