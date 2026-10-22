# Jobs and their connections

R coordinates 22 jobs across three analysis repositories. Each owns its Makefile,
R entry points and runtime bindings. The [job declarations](../workflow/jobs.json)
name parents and stages; the browser shows the same graph.

| Job | Producing inputs |
| --- | --- |
| [Submission](submission/README.md) | supplied source records |
| [Quality check](qc/README.md) | submission |
| [Prepare and load](database/README.md) | QC gate; accepted submission stored in SQLite |
| [Extract](extract/README.md) | database |
| [CPUE A](cpue_a/README.md), [CPUE B](cpue_b/README.md) | extract |
| [CPUE summary](cpue_summary/README.md) → [report](cpue_report/README.md) | CPUE A and B |
| [Prepare A](prepare_a/README.md), [Prepare B](prepare_b/README.md) | extract and corresponding CPUE |
| [Assessment A1](assessment_a1/README.md), [A2](assessment_a2/README.md) | prepare A |
| [Assessment B1](assessment_b1/README.md), [B2](assessment_b2/README.md) | prepare B |
| [Assessment summary](assessment_summary/README.md) → [report](assessment_report/README.md) | all four assessment cases |
| [MSE preparation](mse_prepare/README.md) | all four assessment cases |
| [Constant](mse_constant/README.md), [Index](mse_index/README.md), [Buffered](mse_buffered/README.md) rules | MSE preparation |
| [MSE summary](mse_summary/README.md) → [report](mse_report/README.md) | all three rules |

From the coordinator checkout:

```sh
make job JOB=cpue_a
```

This prepares missing or changed inputs, runs the pinned component and writes
`runs/cpue_a/output.json`, `report.pdf` and `record.json`. The record identifies
input producers, settings, source revision, checksums and actual software.
`runs/state.json` retains the workflow state. `OUTPUT=DIR` selects another folder;
`SETTINGS=FILE` supplies JSON settings.

| Analysis source | Jobs | R library |
| --- | --- | --- |
| [Preparation/CPUE](https://github.com/kyuhank/fisheries-workflow-cpue-demo) | submission through CPUE report (8) | `R/cpue.R` |
| [Assessment](https://github.com/kyuhank/fisheries-workflow-assessment-demo) | preparation through assessment report (8) | `R/assessment.R` |
| [MSE](https://github.com/kyuhank/fisheries-workflow-mse-demo) | preparation through MSE report (6) | `R/mse.R` |

Each component README shows how to run its own Makefile with a supplied context.
Its `jobs/<job>/run.R` defines `calculate(context)`; declared helpers and libraries
are loaded by its R adapter. A copied entry point alone is not standalone.
The MSE repository preserves the exact assessment recurrence helper it needs.

CPUE supplies a relative annual index; assessment preparation joins it with
annual catch in tonnes for consecutive years. Four fixed-growth assessment cases
retain convergence, gradient, boundary, biomass and balance checks. Their
differences are not confidence intervals. MSE compares rules using the same
seeded errors and teaching assumptions; it provides no calibrated stock risk.
Source field definitions, masked-cell handling and units remain in the
[data guide](../data/public/README.md). See [ADAPT.md](../ADAPT.md) for source and
software changes, and [OFFLINE.md](../OFFLINE.md) for saved-run reproduction.
