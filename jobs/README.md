# Jobs and their connections

The 22 jobs use Poisson GLMs for CPUE, a one-parameter RTMB Schaefer assessment
with fixed growth sensitivities, and seeded closed-loop management trials. Each
folder contains an R entry point, such as [run.R](cpue_a/run.R), and a guide to its
inputs, settings and outputs.

```text
jobs/cpue_a/run.R       readable CPUE A entrypoint
jobs/assessment_a1/run.R  fixed-growth RTMB fit
jobs/mse_index/run.R    index-based management trials
jobs/*/README.md        job inputs, settings, outputs and connected jobs
jobs/*_report/report.qmd  concise reports rendered by native Quarto
workflow/r/common.R    row checks, snapshot assembly and input joins
workflow/r/models.R    GLMs, Schaefer objective and RTMB fitting
workflow/r/mse.R       paired seeded management trials and comparisons
workflow/jobs.json     job declarations and input links
workflow/Makefile      R and report recipes inside the container
workflow/engine.py     coordination, SQLite gates and saved records
```

The coordinator follows the input connections, passes outputs between jobs and
records each execution. It calls the R entry points inside the declared immutable
R/RTMB/Quarto container. The browser displays saved results.

## Declare the connections

[`workflow/jobs.json`](../workflow/jobs.json) is the actual job configuration. This
excerpt shows one CPUE-to-assessment path; titles and analyst metadata are omitted:

```json
[
  {"key": "cpue_a", "parents": ["extract"], "run": "jobs/cpue_a/run.R"},
  {"key": "prepare_a", "parents": ["extract", "cpue_a"], "run": "jobs/prepare_a/run.R"},
  {"key": "assessment_a1", "parents": ["prepare_a"], "run": "jobs/assessment_a1/run.R"}
]
```

`workflow/spec.py` checks the declarations. The coordinator prepares required
inputs, starts ready jobs through `workflow/Makefile`, and saves their outputs and
records before dependent jobs continue. The configuration also declares parallel
groups and manual handovers. The demo reads JSON with Python's standard library.

## Follow the jobs

### Data preparation

| Job | Receives from |
| --- | --- |
| [Data submission](submission/README.md) | Supplied synthetic records |
| [Quality check](qc/README.md) | [submission](submission/README.md) |
| [Prepare and load](database/README.md) | [qc](qc/README.md) |
| [Extract data](extract/README.md) | [database](database/README.md) |

### CPUE analysis

| Job | Receives from |
| --- | --- |
| [CPUE analysis A](cpue_a/README.md) | [extract](extract/README.md) |
| [CPUE analysis B](cpue_b/README.md) | [extract](extract/README.md) |
| [Compare CPUE results](cpue_summary/README.md) | [cpue_a](cpue_a/README.md), [cpue_b](cpue_b/README.md) |
| [CPUE report](cpue_report/README.md) | [cpue_summary](cpue_summary/README.md) |

### Stock assessment

| Job | Receives from |
| --- | --- |
| [Prepare inputs A](prepare_a/README.md) | [extract](extract/README.md), [cpue_a](cpue_a/README.md) |
| [Prepare inputs B](prepare_b/README.md) | [extract](extract/README.md), [cpue_b](cpue_b/README.md) |
| [Assessment A1](assessment_a1/README.md) | [prepare_a](prepare_a/README.md) |
| [Assessment A2](assessment_a2/README.md) | [prepare_a](prepare_a/README.md) |
| [Assessment B1](assessment_b1/README.md) | [prepare_b](prepare_b/README.md) |
| [Assessment B2](assessment_b2/README.md) | [prepare_b](prepare_b/README.md) |
| [Compare assessments](assessment_summary/README.md) | [assessment_a1](assessment_a1/README.md), [assessment_a2](assessment_a2/README.md), [assessment_b1](assessment_b1/README.md), [assessment_b2](assessment_b2/README.md) |
| [Assessment report](assessment_report/README.md) | [assessment_summary](assessment_summary/README.md) |

### Management strategy evaluation

| Job | Receives from |
| --- | --- |
| [Prepare MSE](mse_prepare/README.md) | [assessment_a1](assessment_a1/README.md), [assessment_a2](assessment_a2/README.md), [assessment_b1](assessment_b1/README.md), [assessment_b2](assessment_b2/README.md) |
| [Constant catch](mse_constant/README.md) | [mse_prepare](mse_prepare/README.md) |
| [Index rule](mse_index/README.md) | [mse_prepare](mse_prepare/README.md) |
| [Buffered rule](mse_buffered/README.md) | [mse_prepare](mse_prepare/README.md) |
| [MSE results summary](mse_summary/README.md) | [mse_constant](mse_constant/README.md), [mse_index](mse_index/README.md), [mse_buffered](mse_buffered/README.md) |
| [MSE report](mse_report/README.md) | [mse_summary](mse_summary/README.md) |

For **Prepare and load**, QC is the scheduling gate: after the check passes,
the job reads the corrected submission and writes the database snapshot. The
folder guide distinguishes this source artifact from its declared QC dependency.

## Run a job

From the repository root:

```sh
make job JOB=cpue_a
```

Make uses the declared image, pulling it if needed, and starts the coordinator
inside it. The coordinator prepares missing or outdated inputs and uses
`workflow/Makefile` to call `jobs/cpue_a/run.R`. `OUTPUT=DIR` selects an output
directory; `SETTINGS=FILE` supplies settings. When already inside the container,
use `make inside-job JOB=cpue_a`. The run record identifies the container digest
and R/package versions used.

The R bridge passes a named `context` containing settings, decoded parent
results and raw source or SQLite query rows. `calculate(context)` returns
the result. QC can also return corrected submission rows for the coordinator to
save. Database storage and SQL extraction use SQLite; R jobs check their inputs and
calculate results. Report jobs render saved results and records through
`report.qmd` templates without refitting.

```text
runs/cpue_a/output.json  R result
runs/cpue_a/report.html  readable result
runs/cpue_a/record.json  inputs, settings, source hashes and actual container/software
runs/database/snapshot.sqlite  accepted fixed database snapshot
runs/state.json         workflow execution state
```

Biomass uses B/K, intrinsic growth is fixed in each sensitivity case, and MSE
fractions are conditional on the declared stocks, scenarios and seeded trials.
This synthetic example supplies no confidence intervals or real-stock advice.
Assessment records include objective and projected gradients, boundary status,
positive-biomass feasibility and the annual biomass balance residual. The balance
checks the declared recurrence using known catches rather than estimating catches.
The generating truth and units are declared by
[scripts/generate-data.R](../scripts/generate-data.R) and the saved data metadata.

[Browse saved results](https://kyuhank.github.io/fisheries-workflow-demo/example/)
or use **Record** in the [demo](https://kyuhank.github.io/fisheries-workflow-demo/)
to inspect a result's inputs, R source and container. Downloaded runs
include the shared R code, job folders, data and records; one copied job folder
uses these surrounding dependencies.

## Separate repositories

This downloadable example keeps the jobs together. An operational workflow could
place data preparation, CPUE analysis, assessment and MSE in repositories maintained
by their respective teams, or give an individual job its own repository. The
analytical dependencies would still determine which output each job needs. Shared
calculation libraries would also need a recorded version or a preserved copy.

A shared orchestration service would use a job catalogue to resolve each job to
its repository and exact revision, execution command and software environment.
When an upstream job finishes, it would make its output available at a versioned
artifact location, record its checksum and check the expected names, units and
coverage before releasing the dependent job. Each result would retain the exact
input artifact references and source revisions; an upstream revision could then
invalidate only the affected results. A moving branch name alone would not identify
the code or inputs used by a previous result.

The demo currently executes folders in one repository. Connecting independent
repositories would require the service to check out code, transfer artifacts,
control access and use approved execution routes. The folder structure shows
where those job boundaries would lie.

See [ADAPT.md](../ADAPT.md) for adding a job, and
[cloud/README.md](../cloud/README.md) for the current hosted execution.
