# Jobs: inputs, execution and outputs

The demo has 22 jobs. Each folder contains `run.py`, the calculation entry point
used by the workflow, and a short README explaining its incoming artifacts,
settings and outputs. Start with the table below, then follow the input and
next-job links in a folder guide. The job names are the same as those used by
the demo's workflow and orchestration views.

```text
jobs/
  cpue_a/
    README.md       inputs, settings, outputs and connected jobs
    run.py          CPUE A calculation
  prepare_a/
    README.md       how index A and catch enter assessment preparation
    run.py          the preparation calculation
workflow/
  spec.py           dependency graph, roles and execution groups
  engine.py         planning, dispatch, saved outputs and execution records
  models.py         shared CPUE and assessment functions
  mse.py            shared management-trial functions
```

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

```bash
python3 run.py --from cpue_a --scope job
```

The coordinator prepares any missing or outdated upstream inputs, then calls
`jobs/cpue_a/run.py`. Each calculation uses the same shared functions as the live
and offline demo. The job folder therefore uses the surrounding `workflow/`
package; copying that folder alone is not a standalone installation.

Outputs are saved by job under the selected output directory:

```text
runs/cpue_a/
  output.json       calculation result
  report.html       readable result
  record.json       inputs, settings, code hashes and software used
runs/state.json     execution state for the whole workflow
```

The database job also produces `snapshot.sqlite`. Use `--output` to choose another
directory. Without `--scope job`, the selected job and affected downstream jobs
are updated. The coordinator records the job's entry point alongside its shared
code. A change to one job file makes that job's saved result outdated; dependencies
carry the revision downstream. Shared-code changes affect the jobs using that code.

[Browse the saved results](https://kyuhank.github.io/fisheries-workflow-demo/example/)
without running anything, or use **Record** in the
[interactive demo](https://kyuhank.github.io/fisheries-workflow-demo/) to trace the
inputs used by a particular result. **Download this run** includes these job folders,
shared code, data and recorded outputs for reproduction.

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

The current demo coordinates folders in one repository. It does not fetch or
execute other repositories. Connecting independent repositories would require
repository checkout, artifact transport, access controls and approved execution
routes in that service. The folder structure makes the job boundaries visible
without assuming those deployment facilities already exist.

See [ADAPT.md](../ADAPT.md) for adding a job, and
[cloud/README.md](../cloud/README.md) for the current hosted execution.
