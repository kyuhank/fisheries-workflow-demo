# Adapt the workflow

| Change | Source |
| --- | --- |
| Jobs, required inputs, stages and handovers | `workflow/jobs.json` |
| Graph shown in the browser | `app/diagram.json` |
| Scheduling, saved records and bundles | `R/workflow.R` |
| Source pins and checks | `R/sources.R`, `source-lock.template.json` |
| Input mapping, SQLite and receiving contracts | `R/inputs.R`, `workflow/extract-public.sql` |
| Job software and container launch | component `runtime.json`, `R/runtime.R` |
| Scientific calculations | component `jobs/<job>/run.R`, `R/cpue.R`, `R/assessment.R`, `R/mse.R` |
| Result views and formal reports | component `R/render.R`, `reports/results.qmd`, `jobs/*_report/report.qmd` |
| Browser pages from completed outputs | `scripts/build-site.R`, `app/` |

The source lock registers exact revisions of the [CPUE](https://github.com/kyuhank/fisheries-workflow-cpue-demo),
[assessment](https://github.com/kyuhank/fisheries-workflow-assessment-demo) and
[MSE](https://github.com/kyuhank/fisheries-workflow-mse-demo) repositories.
`make hydrate-sources` verifies and assembles these sources in `components/`.
Edit the relevant component in its own checkout, test it, commit the change and
update its source pin before adopting it in the coordinator.

Each repository supplies a standalone interface:

```sh
make -C /path/to/analysis runtime JOB=cpue_a
make -C /path/to/analysis run JOB=cpue_a CONTEXT=/absolute/context.json OUT=/absolute/result
```

Use the job name belonging to that repository. `CONTEXT` supplies the required
parent values and settings; the repository README includes an example. The
Makefile resolves its runtime, mounts source read-only and runs its R adapter.
The coordinator invokes the same component's `inside-job`, `info` and `render`
targets in the selected image. Rendering consumes saved values without refitting.

To change software, set the immutable image digest, platform and package link in
the component's `runtime.json`. Its `default` applies to that analysis; `jobs`
can override one job. A coordinator `runtime-overrides.json` can likewise set
explicit job bindings. Only the resolved entry enters that job's signature.
Shared recipe or R helper edits affect every job using those bytes. Records
identify the actual calculation and rendering image configs, layers and software.

To add a job, declare its parents and stage in `workflow/jobs.json`, register its
component in `R/sources.R`, and provide its component entry point, required
libraries, Make/runtime interface and guide. `calculate(context)` returns a named
result list. Add the same node and edges to `app/diagram.json`; the site builder
checks equality with the job graph. Declare settings in `workflow_job_settings()`
and inputs/units in `R/inputs.R` before testing the new branch.

For another fishery, first review source fields, units, missing/suppressed cells,
SQL selection and CPUE prediction support. Annual catch in tonnes is separate
from the fleet CPUE observations. Keep source releases and notices. Then review
fixed-growth assessment assumptions, diagnostics and the shared seeded MSE
scenarios. The example does not establish validated stock advice.

`make run OUTPUT=runs` calculates and renders results. `make site OUTPUT=runs`
builds pages from those completed files and rejects mismatched sources or
artifacts. Packaging uses `scripts/release.R`; it keeps the exact source closure,
reference records, comparison policy and runtime catalogue. Preserve all required
image archives with the download, as described in [OFFLINE.md](OFFLINE.md).
Earlier release ZIPs retain their original sources and instructions.
