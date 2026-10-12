# Index rule (`mse_index`)

Test advice proportional to the three-year mean observed abundance index in the common seeded Schaefer management trials.

**Path:** Shared trials → index-based catch → catch and biomass outcomes.

**Inputs:** Stocks, scenarios and saved `error_streams` in `runs/mse_prepare/output.json`.

**From:** [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md).

**Settings:** No job-specific settings (`{}`).

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=mse_index
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/mse_index/output.json` | saved calculation result |
| `runs/mse_index/report.html` | result page from [shared renderer](../../workflow/reports.py) |
| `runs/mse_index/record.json` | producing inputs, settings, exact code and software |

**Used by:** [MSE results summary (`mse_summary`)](../mse_summary/README.md).

[Saved report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_index/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_index/record.json)
