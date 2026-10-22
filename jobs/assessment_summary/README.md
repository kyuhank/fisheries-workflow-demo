# Compare assessments (`assessment_summary`)

Compare the four fixed-growth Schaefer sensitivity cases, their biomass trajectories and fit diagnostics.

**Path:** Four fitted cases → compare trajectories → sensitivity summary.

**Inputs:** The fitted `series`, r, K, convergence and bounds in all four assessment outputs.

**From:** [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md), [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md).

**Settings:** No job-specific settings (`{}`).

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=assessment_summary
```

[run.R](https://github.com/kyuhank/fisheries-workflow-assessment-demo/blob/0b7071600b636b17edacd00ed216af2aff19090a/jobs/assessment_summary/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/assessment_summary/output.json` | saved calculation result |
| `runs/assessment_summary/report.pdf` | compiled Quarto result PDF |
| `runs/assessment_summary/report.html` | result page from [component renderer](https://github.com/kyuhank/fisheries-workflow-assessment-demo/blob/0b7071600b636b17edacd00ed216af2aff19090a/R/render.R) |
| `runs/assessment_summary/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Assessment report (`assessment_report`)](../assessment_report/README.md).

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_summary/record.json)
