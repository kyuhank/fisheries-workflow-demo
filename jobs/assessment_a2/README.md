# Assessment A2 (`assessment_a2`)

Fit the toy Schaefer model to index A with the selected fixed intrinsic growth and initial biomass equal to K. RTMB estimates one log(K) parameter; catchability q is profiled.

**Path:** Annual index and catches → fixed-growth Schaefer fit → biomass trajectory.

**Inputs:** Joined index and catch `rows` in `runs/prepare_a/output.json`.

**From:** [Prepare inputs A (`prepare_a`)](../prepare_a/README.md).

**Settings:** `growth_rate_2` saved as `r` (default: 0.30; choices: 0.25, 0.30, 0.35).

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=assessment_a2
```

[run.R](https://github.com/kyuhank/fisheries-workflow-assessment-demo/blob/6798a63a0ee7d5975d1d1fa2027284073015e0ee/jobs/assessment_a2/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/assessment_a2/output.json` | saved calculation result |
| `runs/assessment_a2/report.pdf` | compiled Quarto result PDF |
| `runs/assessment_a2/report.html` | result page from [component renderer](https://github.com/kyuhank/fisheries-workflow-assessment-demo/blob/6798a63a0ee7d5975d1d1fa2027284073015e0ee/R/render.R) |
| `runs/assessment_a2/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Compare assessments (`assessment_summary`)](../assessment_summary/README.md), [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md).

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a2/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a2/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a2/record.json)
