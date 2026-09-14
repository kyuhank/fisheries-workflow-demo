# Fisheries workflow demonstration

[Open the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Download for offline use](https://github.com/kyuhank/fisheries-workflow-demo/releases)

Follow a change from fisheries data through assessment to management strategy evaluation. See which jobs
need to run again, which results can be kept, and where each output came from.
Synthetic data and simplified models demonstrate how these analyses can be connected.

## Choose a mode

| Mode | What happens |
| --- | --- |
| **Live run** | GitHub downloads the recorded Docker image and calculates new results, using synthetic data from PostgreSQL. No login is needed. |
| **Offline run** | The same Python analysis runs in your browser. The website downloads Python when first needed; the offline HTML already includes it. |
| **View example** | Open completed reports and their input records. No code runs. |

If the live service cannot connect, the page switches to **Offline run** and
explains the change. Press **Run** to start; no analysis starts automatically.
For use without an internet connection, select **Download offline demo** on the website, or use
`index.html` from a published release. These files include Python, data and saved
reports; saving the lightweight website page alone does not include Python.

## Follow the connections

Run the workflow, then change the **CPUE A records** selection. Follow the revised
analysis into the assessments that use it; unaffected results keep their original
files and run records. **Orchestration tool** shows each job's owner, progress,
inputs and outputs. Open **Inputs & versions** to trace the data, code and software
behind a result, or use **Reproduce & compare** to check it again.

Summaries compare results in plots and tables. Reports provide a short account
of the methods and findings, linked to the results used to write them.

The MSE task uses the four fitted assessment cases to test three simple catch
rules under two future recruitment scenarios. **Prepare MSE** shows what comes
from each assessment. Simulated observations inform catch decisions, which affect
the stock and its next observation. **Compare strategies** summarises the trials;
**MSE report** describes the results and their limits.

Parallel CPUE analyses, input preparations, assessment fits and management trials finish their
peer group before dependent stages start. Partial reruns retain unaffected peers.

**Manual handover** represents separate analyst workspaces without shared
orchestration. Receiving analyses wait for updated files, while independent work
can continue: CPUE summaries and reports run while assessment preparation waits
for the CPUE files. Click **Confirm file transfer** to release the highlighted
branches. The click represents an analyst's handover; it does not upload files
or measure staff time.

**Download this run** keeps its code, data, settings and results. Live sessions are
separate; temporary results expire after 10 minutes and are replaced by later runs.
Scheduled maintenance removes old execution logs. Published versions are retained.

## Run locally

```bash
python3 run.py
python3 run.py --from prepare_a
make container
```

Open `runs/assessment_report/report.html` or `runs/mse_report/report.html`. Use Python 3.12 or later; no additional
Python packages are needed. Docker needs its image locally or a connection to
download it. `make check` runs the checks; `make html` rebuilds the page.

See [ADAPT.md](ADAPT.md) to adapt the workflow, [cloud/README.md](cloud/README.md)
for hosting, and [THIRD_PARTY.md](THIRD_PARTY.md) for software sources and licences.
