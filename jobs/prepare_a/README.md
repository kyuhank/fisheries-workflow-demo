# Prepare inputs A (`prepare_a`)

Join CPUE index A to annual catches by year and reject an index year without a matching catch.

**Path:** Index A and annual catches → join by year → assessment inputs A.

**Inputs:** The index `series` in `runs/cpue_a/output.json` and annual `catch` in `runs/extract/output.json`.

**From:** [Extract data (`extract`)](../extract/README.md), [CPUE analysis A (`cpue_a`)](../cpue_a/README.md).

**Settings:** No job-specific settings (`{}`).

From the repository root, run this job and prepare any required inputs:

```sh
make job JOB=prepare_a
```

[run.R](https://github.com/kyuhank/fisheries-workflow-assessment-demo/blob/6798a63a0ee7d5975d1d1fa2027284073015e0ee/jobs/prepare_a/run.R) is the entry point. It receives the coordinator’s named
`context` and uses the recorded shared libraries; a copied script is not standalone.
See the [job guide](../README.md) for container and output options.

| Saved file | Contents |
| --- | --- |
| `runs/prepare_a/output.json` | saved calculation result |
| `runs/prepare_a/report.pdf` | compiled Quarto result PDF |
| `runs/prepare_a/report.html` | result page from [component renderer](https://github.com/kyuhank/fisheries-workflow-assessment-demo/blob/6798a63a0ee7d5975d1d1fa2027284073015e0ee/R/render.R) |
| `runs/prepare_a/record.json` | producing inputs, settings, exact code and software |

**Used by:** [Assessment A1 (`assessment_a1`)](../assessment_a1/README.md), [Assessment A2 (`assessment_a2`)](../assessment_a2/README.md).

[Saved report (PDF)](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/report.pdf) · [HTML](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/report.html) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/prepare_a/record.json)
