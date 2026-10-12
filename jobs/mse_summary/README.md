# MSE results summary (`mse_summary`)

Compare the three rules only when fitted stocks, scenarios and the actual saved error vectors match. Summarise catches, biomass and catch stability.

**Path:** Three rule outputs → compare trial metrics → management comparison.

**Inputs:** Completed constant, index and buffered rule outputs, including their actual common error vectors.

**From:** [Constant catch (`mse_constant`)](../mse_constant/README.md), [Index rule (`mse_index`)](../mse_index/README.md), [Buffered rule (`mse_buffered`)](../mse_buffered/README.md).

**Settings:** No job-specific settings (`{}`).

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=mse_summary
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/mse_summary/output.json` | saved calculation result |
| `runs/mse_summary/report.html` | result page from [shared renderer](../../workflow/reports.py) |
| `runs/mse_summary/record.json` | producing inputs, settings, exact code and software |

**Used by:** [MSE report (`mse_report`)](../mse_report/README.md).

[Saved report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_summary/record.json)
