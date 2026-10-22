# Compare CPUE results (`cpue_summary`)

Compare the two saved CPUE indices without fitting another model.

**Path:** Indices A and B → align years → index comparison.

**Inputs:** The `series` and method metadata in `runs/cpue_a/output.json` and `runs/cpue_b/output.json`.

**From:** [CPUE analysis A (`cpue_a`)](../cpue_a/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md).

**Settings:** No job-specific settings (`{}`).

The result preserves both producing methods, prediction support, weights, units and checks. A uses a cell–quarter adjustment; B adjusts for quarter only.

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=cpue_summary
```

[run.R](https://github.com/kyuhank/fisheries-workflow-cpue-demo/blob/d4454fcfa9a23bd590344ad92940a13fa0a41c06/jobs/cpue_summary/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/cpue_summary/output.json` | saved calculation result |
| `runs/cpue_summary/report.pdf` | compiled Quarto result PDF |
| `runs/cpue_summary/report.html` | result page from [component renderer](https://github.com/kyuhank/fisheries-workflow-cpue-demo/blob/d4454fcfa9a23bd590344ad92940a13fa0a41c06/R/render.R) |
| `runs/cpue_summary/record.json` | producing inputs, settings, exact code and software |

**Used by:** [CPUE report (`cpue_report`)](../cpue_report/README.md).

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_summary/record.json)
