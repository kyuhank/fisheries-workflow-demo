# Fisheries workflow demonstration

[Open the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Orchestration tool](https://kyuhank.github.io/fisheries-workflow-demo/#orchestration) · [Download](https://github.com/kyuhank/fisheries-workflow-demo/releases)

Follow a change from data preparation through CPUE analysis, stock assessment and
management strategy evaluation (MSE). Inspect each result's inputs, code and
software, then rerun the analyses affected by a revision.

Synthetic data and simple models illustrate the workflow. They provide no advice
for a real fishery.

## Run the demo

| Mode | What happens |
| --- | --- |
| **Live run** | GitHub Actions runs Python in the recorded Docker image, using synthetic records from PostgreSQL. No login is needed. |
| **Offline run** | The same Python analysis runs in your browser. The downloaded HTML includes Python and the data. |
| **View example** | Open saved outputs and records without running code. |

Run the workflow once, then change **CPUE A records**, **Mortality setting 2** or
**MSE catch buffer**. Use **Update workflow** to update affected jobs; unchanged
results keep their original records. **Orchestration tool** groups numbered jobs
under **Tasks**. Click a job to open its output. Its **Run** action runs that job,
first preparing any missing or outdated upstream inputs. Other results stay in
place; use **Update workflow** to update jobs that depend on the revised output.
Both views follow the same execution. **Dependencies** shows connected jobs;
**Record** shows saved inputs and versions, with **Reproduce & compare** to check a result.

MSE compares three catch rules using the four fitted assessment cases. A scenario
with reduced recruitment followed by recovery shows how observed indices, catch
decisions and stock changes interact. The Buffered rule uses index thresholds and
a catch buffer, with advice changes limited to 15% per year. Changing the buffer
updates that rule, the MSE summary and the report when **Update workflow** is used.

**Manual handover** represents separate workspaces without shared orchestration.
Click **Confirm file transfer** to release waiting analyses. Independent work,
such as CPUE or assessment reporting, continues while a transfer is pending. No file upload is
required.

If the live service cannot connect, a notice explains the switch to **Offline
run**. Press **Run** to start. For use without internet access, download
`fisheries-workflow.html` from a release; saving the website page alone does not
include Python.

**Download this run** saves its code, data, settings and outputs. Live results
expire after ten minutes of inactivity; the next run can rebuild missing inputs.
Releases and downloaded files remain available independently of the live service.
Follow the archive's `REPRODUCE.txt` to repeat and compare a run. For a single-job
run, it checks the selected output; other saved results keep their original records.

## Run locally

Use Python 3.12 or later; no extra Python packages are required.

```bash
python3 run.py
python3 run.py --from prepare_a
python3 run.py --from prepare_a --scope job
```

By default, `--from` also reruns jobs that use the selected job's output.
With `--scope job`, only the selected job and any missing or outdated upstream
inputs run.

Open `runs/assessment_report/report.html` or `runs/mse_report/report.html`.
`make container` runs in Docker, `make check` checks the workflow, and `make html`
builds the website and offline download.

See [ADAPT.md](ADAPT.md) for the code structure, [cloud/README.md](cloud/README.md)
for hosting, and [THIRD_PARTY.md](THIRD_PARTY.md) for software sources and licences.
