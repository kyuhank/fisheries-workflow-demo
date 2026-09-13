# Fisheries workflow demonstration

[Open the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Download for offline use](https://github.com/kyuhank/fisheries-workflow-demo/releases)

Follow a change from fisheries data through analysis to assessment. See which jobs
need to run again, which results can be kept, and where each output came from.
The data are synthetic and the models are simplified.

## Choose a mode

| Mode | What happens |
| --- | --- |
| **Live run** | GitHub downloads the recorded Docker image and calculates new results, using synthetic data from PostgreSQL. No login is needed. |
| **Offline run** | The same Python analysis runs in your browser. The website downloads Python when first needed; the offline HTML already includes it. |
| **View example** | Open completed reports and their input records. No code runs. |

If the live service is unavailable, select **Offline run**. For use without an
internet connection, select **Download offline demo** on the website, or use
`index.html` from a published release. These files include Python, data and saved
reports; saving the lightweight website page alone does not include Python.

## Follow the connections

Run the workflow, then change the **CPUE A records** selection. Its dependent jobs
update; other results retain their original files and run records. **Orchestration
tool** groups jobs into tasks and shows each job's owner, progress, inputs and
outputs. Open **Inputs & versions** to follow an output back to its sources or
use **Reproduce & compare** to check it again.

Parallel CPUE analyses, input preparations and assessment fits each finish their
peer group before dependent stages start. Partial reruns retain unaffected peers.

**Manual handover** represents separate analyst workspaces without shared
orchestration. Both affected branches show **Awaiting file** until you click
**Confirm file transfer**; one confirmation covers the highlighted boundary.
CPUE summaries and reports continue while assessment waits for the CPUE files.
The pauses do not represent measured staff time.

**Download this run** keeps its code, data, settings and results. Live sessions are
separate; temporary results expire after 10 minutes and are replaced by later runs.
Scheduled maintenance removes old execution logs. Published versions are retained.

## Run locally

```bash
python3 run.py
python3 run.py --from prepare_a
make container
```

Open `runs/assessment_report/report.html`. Use Python 3.12 or later; no additional
Python packages are needed. Docker needs its image locally or a connection to
download it. `make check` runs the checks; `make html` rebuilds the page.

See [ADAPT.md](ADAPT.md) to adapt the workflow, [cloud/README.md](cloud/README.md)
for hosting, and [THIRD_PARTY.md](THIRD_PARTY.md) for software sources and licences.
