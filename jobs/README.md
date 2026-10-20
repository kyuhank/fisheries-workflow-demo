# Jobs and their connections

The 22 jobs pass public catch and effort data through CPUE, assessment and MSE.
Each guide states its input → method → output path. The calculations use
quasipoisson CPUE GLMs, fixed-growth RTMB Schaefer fits and seeded management
trials. These simplified models provide no real-stock advice.

| Job | Required producing jobs |
| --- | --- |
| [Data submission](submission/README.md) | supplied records |
| [Quality check](qc/README.md) | `submission` |
| [Prepare and load](database/README.md) | `qc` |
| [Extract data](extract/README.md) | `database` |
| [CPUE analysis A](cpue_a/README.md) | `extract` |
| [CPUE analysis B](cpue_b/README.md) | `extract` |
| [Compare CPUE results](cpue_summary/README.md) | `cpue_a`, `cpue_b` |
| [CPUE report](cpue_report/README.md) | `cpue_summary` |
| [Prepare inputs A](prepare_a/README.md) | `extract`, `cpue_a` |
| [Prepare inputs B](prepare_b/README.md) | `extract`, `cpue_b` |
| [Assessment A1](assessment_a1/README.md) | `prepare_a` |
| [Assessment A2](assessment_a2/README.md) | `prepare_a` |
| [Assessment B1](assessment_b1/README.md) | `prepare_b` |
| [Assessment B2](assessment_b2/README.md) | `prepare_b` |
| [Compare assessments](assessment_summary/README.md) | `assessment_a1`, `assessment_a2`, `assessment_b1`, `assessment_b2` |
| [Assessment report](assessment_report/README.md) | `assessment_summary` |
| [Prepare MSE](mse_prepare/README.md) | `assessment_a1`, `assessment_a2`, `assessment_b1`, `assessment_b2` |
| [Constant catch](mse_constant/README.md) | `mse_prepare` |
| [Index rule](mse_index/README.md) | `mse_prepare` |
| [Buffered rule](mse_buffered/README.md) | `mse_prepare` |
| [MSE results summary](mse_summary/README.md) | `mse_constant`, `mse_index`, `mse_buffered` |
| [MSE report](mse_report/README.md) | `mse_summary` |

For **Prepare and load**, QC is the scheduling gate. The accepted submission is
the source artifact stored in SQLite; its record is retained alongside the QC result.

## Read and adapt a job

The [job declarations](../workflow/jobs.json) name the entry point and its parent
jobs. The coordinator starts a job when required inputs are ready and records
the producing run, signature and file checksum before passing its result onward.

An R entry point receives a named `context` and returns a result. For example,
[CPUE A](cpue_a/run.R) uses the shared CPUE function:

```r
calculate <- function(context) {
  cpue(context$parents$extract$sets, stratum_effect = TRUE,
       min_hooks = context$settings$min_hooks_a)
}
```

For public records, this fits year and cell–quarter effects with a log effort
offset. The saved result contains the prediction grid and weights as well as the
annual index. The same entry point retains the earlier synthetic-vessel example.
Shared libraries are loaded by the R driver; a copied `run.R` is not standalone.

To adapt a fishery, first map its source fields and units, then review the saved
SQL and CPUE prediction support. Change later assessment and management assumptions
only after checking their inputs and receiving contracts. [ADAPT.md](../ADAPT.md)
explains adding jobs, declaring connections and changing source pins.

| File | Purpose |
| --- | --- |
| `jobs/*/run.R` | one named calculation |
| `jobs/*_report/report.qmd` | complete analysis reports from saved results |
| `workflow/results.qmd` | concise Quarto result views; plots use saved numerical outputs |
| `workflow/r/common.R` | row checks, source selection and annual joins |
| `workflow/r/models.R` | monorepo CPUE and Schaefer functions |
| `workflow/r/mse.R` | management trials with shared random errors |
| `workflow/jobs.json` | parents, execution stages and handovers |
| `workflow/engine.py` | scheduling, saved records and reuse |

## Run and inspect a job

From the repository root, with Docker, Make, Python 3 and Git available:

```sh
make job JOB=cpue_a
```

This runs the pinned component revision. For local job or model edits in this
checkout, use `PAPER_SOURCE_MODE=monorepo make job JOB=cpue_a`; adopting a change
in the default route requires updating the component repository and source pin.

The coordinator prepares missing or changed inputs and calls the R script in
the recorded container. `OUTPUT=DIR` selects the result directory;
`SETTINGS=FILE` supplies JSON settings. Inside the declared container, use
`make inside-job JOB=cpue_a`.

| File | Contents |
| --- | --- |
| `runs/cpue_a/output.json` | numerical result and method metadata |
| `runs/cpue_a/report.pdf` | compiled Quarto result PDF |
| `runs/cpue_a/record.json` | input producers, settings, exact code and software |
| `runs/database/snapshot.sqlite` | accepted data snapshot |
| `runs/state.json` | execution state and events |

CPUE transfers supply annual relative `index` values. Preparation joins these
to `catch_t` in tonnes for matching consecutive years. Assessment records retain
convergence, gradient, boundary, positive-biomass and annual balance checks.
Differences among the four fixed-growth cases are not confidence intervals.

MSE preparation receives positive finite growth, capacity and catchability,
the observed indices and catches, and the declared next-year biomass. The
management trials use the same seeded errors for each rule. Trial fractions are
conditional comparisons under the supplied cases and scenarios.

## Separate repositories

The source lock records exact revisions from three component repositories:

| Repository | Jobs | Calculation library |
| --- | --- | --- |
| [Preparation/CPUE](https://github.com/kyuhank/fisheries-workflow-cpue-demo) | submission through CPUE report (8) | `R/cpue.R` |
| [Assessment](https://github.com/kyuhank/fisheries-workflow-assessment-demo) | input preparation through assessment report (8) | `R/assessment.R` |
| [MSE](https://github.com/kyuhank/fisheries-workflow-mse-demo) | MSE preparation through MSE report (6) | `R/mse.R` |

The coordinator verifies the source bytes named in
[source-lock.template.json](../source-lock.template.json). Shared row and JSON
handling stays in `workflow/r/common.R`. MSE preparation also uses the declared
assessment library. Downloaded runs contain the exact component snapshots and
origin manifests; unchanged dependencies keep their producing records.
[ADAPT.md](../ADAPT.md#separate-analyst-repositories) describes source assembly and
the explicit monorepo fallback. Repository separation uses one coordinator and
does not establish collaboration by several human operators.
