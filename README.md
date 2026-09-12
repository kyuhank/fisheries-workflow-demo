# Fisheries workflow

[Run the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Download a version](https://github.com/kyuhank/fisheries-workflow-demo/releases)

An executable example connecting data preparation, CPUE analysis and stock assessment.
All observations are synthetic and the models are illustrative. The data describe increasing then easing catches, a decline and partial recovery in abundance, and changing vessel composition. These trends make the workflow visible; they are not findings about a real stock.

Operational assessments also prepare size, age and tagging data and run many
diagnostics and model comparisons. This smaller example shows how those steps
can be connected and recorded.

Open **index.html** from a downloaded release. Python and SQLite run inside the
browser; no login, installation or internet connection is required. Each visitor
has a separate execution. **Live analysis** is the default. **Saved example**
opens a completed workflow with every job's report, data and log, without running
code. The `example/` folder also provides plain HTML reports.

1. Run the full workflow and follow the quality check and corrected submission.
2. Select **Input prep A** and run again. Earlier data and CPUE results are retained.
3. Select **CPUE report**. Only that reporting job runs.

Switch **Connection** to **Manual handover** to pause where files must pass
between analysts. **Transfer files** continues the actual calculation. After a
full run, **Revise CPUE A** changes the effort filter: the earlier assessment
remains visible until its inputs are passed on and the dependent work is rerun.
**Connect automatically** removes the remaining transfer pauses. These pauses
illustrate coordination; they do not measure staff time or send messages.

**Orchestration tool** groups jobs into tasks and shows owners, inputs, status, logs and
outputs. **Download this run** saves the analysis code, data, settings and results.
Owner labels illustrate responsibilities; each browser tab runs independently.

## Run the same code with Python

```bash
python3 run.py
python3 run.py --from prepare_a
```

Open `runs/assessment_report/report.html`. Python 3.12 or later is recommended;
no third-party Python packages are needed.

## Container and checks

```bash
make container
make check
```

The container uses a fixed image. CI runs the checks in that image when code
changes. Browser execution uses the preserved Pyodide runtime; both execute
`workflow/`. Their software versions are recorded with the results.

`scripts/generate-data.py` creates the fixed illustrative data. `workflow/spec.py` defines jobs and dependencies; `workflow/models.py` contains
the calculations; `app/` contains the interface. See [ADAPT.md](ADAPT.md) to use
this structure for another analysis and [THIRD_PARTY.md](THIRD_PARTY.md) for sources.

Release bundles contain the runtime, code, data and a reference report.
Keep a release rather than relying on a moving branch or live web service.

To rebuild the browser page, run `make html`. Optional browser checks use
Playwright: `python3 scripts/check-browser.py`. They open the local HTML with
network access disabled and compare its calculations with Python outputs.
