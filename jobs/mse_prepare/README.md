# Prepare MSE (`mse_prepare`)

Reconstruct next-year Schaefer stocks after the terminal assessment catch, then prepare common seeded growth and observation errors once for all three management rules.

**Path:** Four fitted cases → define future trials → shared simulation inputs.

**Inputs:** All four assessment outputs: r, K, q, annual catches, observed indices and the declared next-year biomass.

**From:** [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md), [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md).

**Settings:** No job-specific settings (`{}`).

MSE must be enabled (`"mse": true`). The declared trials use 15 years, 20 paired replicates per fitted case and growth scenario, with catches capped at 40% of current biomass.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=mse_prepare
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/mse_prepare/output.json` | saved calculation result |
| `runs/mse_prepare/report.html` | result page from [shared renderer](../../workflow/reports.py) |
| `runs/mse_prepare/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Constant catch (`mse_constant`)](../mse_constant/README.md), [Index rule (`mse_index`)](../mse_index/README.md), [Buffered rule (`mse_buffered`)](../mse_buffered/README.md).

[Saved report](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_prepare/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_prepare/record.json)
