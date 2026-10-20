# Prepare inputs B (`prepare_b`)

Join CPUE index B to annual catches by year and reject an index year without a matching catch.

**Path:** Index B and annual catches → join by year → assessment inputs B.

**Inputs:** The index `series` in `runs/cpue_b/output.json` and annual `catch` in `runs/extract/output.json`.

**From:** [Extract data (`extract`)](../extract/README.md), [CPUE analysis B (`cpue_b`)](../cpue_b/README.md).

**Settings:** No job-specific settings (`{}`).

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=prepare_b
```

[run.R](run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md#run-and-inspect-a-job) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/prepare_b/output.json` | saved calculation result |
| `runs/prepare_b/report.pdf` | compiled Quarto result PDF |
| `runs/prepare_b/report.html` | result page from [shared renderer](../../workflow/reports.py) |
| `runs/prepare_b/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Assessment B1 (`assessment_b1`)](../assessment_b1/README.md), [Assessment B2 (`assessment_b2`)](../assessment_b2/README.md).

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_b/record.json)
