# CPUE report (`cpue_report`)

Render the saved CPUE comparison as a Quarto report. The report reads the result and run record without refitting the GLMs.

**Path:** Saved index comparison → describe methods and values → CPUE report.

**Inputs:** `runs/cpue_summary/output.json` and the report job's saved run record.

**From:** [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md).

**Settings:** No job-specific settings (`{}`).

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=cpue_report
```

[run.R](https://github.com/kyuhank/fisheries-workflow-cpue-demo/blob/d4454fcfa9a23bd590344ad92940a13fa0a41c06/jobs/cpue_report/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/cpue_report/output.json` | saved calculation result |
| `runs/cpue_report/report.pdf` | compiled Quarto result PDF |
| `runs/cpue_report/report.html` | result page from [report.qmd](https://github.com/kyuhank/fisheries-workflow-cpue-demo/blob/d4454fcfa9a23bd590344ad92940a13fa0a41c06/jobs/cpue_report/report.qmd) |
| `runs/cpue_report/record.json` | producing inputs, settings, exact code and software |

**Used by:** None.

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/record.json)
