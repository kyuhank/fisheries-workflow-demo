# Fisheries workflow demonstration

[Open the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Orchestration tool](https://kyuhank.github.io/fisheries-workflow-demo/#orchestration) · [Download](https://github.com/kyuhank/fisheries-workflow-demo/releases)

Follow a data revision through CPUE analysis, stock assessment and management
strategy evaluation (MSE). Inspect the inputs, code and software behind each
result, then rerun the affected analyses.

Synthetic data and simple models illustrate the workflow. They provide no advice
for a real fishery.

## Run the demo

| Mode | What happens |
| --- | --- |
| **Live run** | GitHub Actions runs the R jobs inside the recorded Docker image, using synthetic records from PostgreSQL. No login is needed. |
| **View example** | Open saved outputs and records without running code. |

The **Workflow diagram** shows which outputs each job needs. **Orchestration tool**
uses these connections to start affected jobs inside the recorded container when
their inputs are ready. It groups jobs by task and shows example analyst roles,
progress and execution records. Switch between the views to follow the same run.

Run the workflow once, then change **CPUE A records**, **Growth-rate setting 2** or
**MSE catch buffer**. **Update workflow** reruns affected jobs and retains the
original records for unchanged results. Under **Tasks**, click a job to open its
output. **Run** executes that job after preparing any missing or outdated inputs;
use **Update workflow** to continue through its dependents. **Dependencies** shows
connected jobs. **Record** shows saved inputs and versions, with
**Reproduce & compare** to check a result.

MSE compares three catch rules using the four fitted assessment cases. A scenario
with reduced growth followed by recovery shows how observed indices, catch
decisions and stock changes interact. The Buffered rule uses index thresholds and
a catch buffer, with advice changes limited to 15% per year. Changing the buffer
updates that rule, the MSE summary and the report when **Update workflow** is used.

**Manual handover** represents separate workspaces without shared orchestration.
Click **Confirm file transfer** to release waiting analyses. Independent work,
such as CPUE or assessment reporting, continues while a transfer is pending.
The demonstration requires no file upload.

If the live service cannot connect, a notice offers **View example**. Download
`fisheries-workflow.html` from a release to view saved results without internet
access. New calculations require the container.

**Download this run** saves its code, data, settings and outputs, including the
actual synthetic records supplied to a Live execution. Live results
expire after ten minutes of inactivity; the next run can rebuild missing inputs.
Releases and downloaded files remain available independently of the live service.
Follow the archive's `REPRODUCE.txt` to repeat and compare a run. For a single-job
run, it checks the selected output; other saved results keep their original records.

## Explore the jobs

Open [jobs/](jobs/README.md) to follow the 22 jobs in execution order. Each folder
contains an R entry point and a guide to its inputs, settings, outputs and
connected jobs. For example,
[CPUE A](jobs/cpue_a/README.md) reads the extracted observations, produces an
index and supplies [assessment preparation A](jobs/prepare_a/README.md).
The demo's **Record** view also links to the corresponding job folder.

This example keeps the jobs in one repository so its code and synthetic data can
be downloaded together. In an operational workflow, different teams could maintain
these jobs in separate repositories. The
[repository guide](jobs/README.md#separate-repositories) explains how a shared
orchestration service would connect their versioned inputs and outputs.

## Repeat a run with Docker

All calculations run inside the preserved Linux AMD64 container, which supplies
R, RTMB, Quarto and the required packages. The coordinator schedules jobs, checks
inputs and records outputs. CPUE uses Poisson GLMs; assessment uses a small RTMB
surplus-production model. Management trials share the prepared cases and recorded
random errors. The three reports are rendered from QMD.

Use **Download this run** and follow its `REPRODUCE.txt`. It gives the exact image
digest, the pull and run instructions, and a comparison with the saved results.
Docker on an ARM computer requires AMD64 emulation. After the image has been
pulled, the downloaded analysis can run without network access.

From the repository root, `make run` runs the workflow and `make job JOB=cpue_a`
runs one job with its required inputs. In an extracted run download, use
`make reproduce` and `make compare`; its `REPRODUCE.txt` gives any single-job
selection and the recorded image. `make check` checks calculations and coordination,
and `make html` builds the pages and offline reader. The host requires Docker and
Make; the image supplies Python, R and Quarto. The root Makefile provides these
commands; `workflow/Makefile` contains the short R and report recipes. Open
`runs/assessment_report/report.html` or `runs/mse_report/report.html`.

See [ADAPT.md](ADAPT.md) for the code structure, [cloud/README.md](cloud/README.md)
for hosting, and [THIRD_PARTY.md](THIRD_PARTY.md) for software sources and licences.
