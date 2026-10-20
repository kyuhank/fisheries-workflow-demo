# Assessment report (`assessment_report`)

Render the saved assessment comparison as a Quarto report. The report describes the fixed assumptions, convergence and bounds without refitting or claiming confidence intervals.

**Path:** Saved assessment comparison → describe cases and checks → assessment report.

**Inputs:** `runs/assessment_summary/output.json` and the report job's saved run record.

**From:** [Compare assessments (`assessment_summary`)](../assessment_summary/README.md).

**Settings:** No job-specific settings (`{}`).

Biomass is reported as B/K and catches in tonnes. Growth and initial depletion are fixed sensitivity assumptions; convergence does not establish real-stock validity or uncertainty.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=assessment_report
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/assessment_report/output.json` | saved calculation result |
| `runs/assessment_report/report.pdf` | compiled Quarto result PDF |
| `runs/assessment_report/report.html` | result page from [report.qmd](report.qmd) |
| `runs/assessment_report/record.json` | producing inputs, settings, exact code and software |

**Used by:** None.

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/record.json)
