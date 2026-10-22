# Assessment A1 (`assessment_a1`)

Fit the toy Schaefer model to index A with fixed intrinsic growth r = 0.25 and initial biomass equal to K. RTMB estimates one log(K) parameter; catchability q is profiled.

**Path:** Annual index and catches → fixed-growth Schaefer fit → biomass trajectory.

**Inputs:** Joined index and catch `rows` in `runs/prepare_a/output.json`.

**From:** [Prepare inputs A (`prepare_a`)](../prepare_a/README.md).

**Settings:** Fixed `r = 0.25`.

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=assessment_a1
```

[run.R](https://github.com/kyuhank/fisheries-workflow-assessment-demo/blob/0b7071600b636b17edacd00ed216af2aff19090a/jobs/assessment_a1/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/assessment_a1/output.json` | saved calculation result |
| `runs/assessment_a1/report.pdf` | compiled Quarto result PDF |
| `runs/assessment_a1/report.html` | result page from [component renderer](https://github.com/kyuhank/fisheries-workflow-assessment-demo/blob/0b7071600b636b17edacd00ed216af2aff19090a/R/render.R) |
| `runs/assessment_a1/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Compare assessments (`assessment_summary`)](../assessment_summary/README.md), [Prepare MSE (`mse_prepare`)](../mse_prepare/README.md).

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a1/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a1/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_a1/record.json)
