# Fisheries workflow

[Run the demonstration](https://kyuhank.github.io/fisheries-workflow-demo/) · [Download a version](https://github.com/kyuhank/fisheries-workflow-demo/releases)

An executable example connecting data preparation, CPUE analysis and stock assessment.
All observations are synthetic; the simple models illustrate the workflow, not an actual stock.
Operational assessments contain additional inputs, diagnostics and model comparisons.

## Three ways to explore

- **Online · GitHub Actions** downloads the recorded Docker image and calculates results on a free standard runner, using synthetic records from PostgreSQL. No reader account or installation is needed.
- **Offline · browser calculation** runs the included Python code and data in the browser. A downloaded `index.html` works without an internet connection or maintained web service.
- **Saved example** opens previously calculated reports, data and records without running code. Plain HTML reports are also included in `example/`.

Run the full workflow, then select **Input prep A** and run again. Earlier data and
CPUE results retain their original records. Selecting **CPUE report** repeats only
that reporting job. **Orchestration tool** groups jobs into tasks and gives access
to responsibilities, inputs, progress, logs and outputs.

Select **Manual handover** to pause where files pass between analyses. **Transfer
files** continues the calculation. After a full run, **Revise CPUE A** changes the
effort filter: the earlier assessment stays visible until the new inputs are
passed on and the dependent work is repeated. The pauses illustrate coordination;
no message is sent and no staff response time is assumed.

**Download this run** saves its code, data, settings, records and reference results.
Online sessions are separate. Their latest results expire after 10 minutes;
previous temporary runs are replaced. GitHub demonstration logs are cleared by a
scheduled maintenance workflow. Published releases and saved examples are retained.

## Python and container

```bash
python3 run.py
python3 run.py --from prepare_a
make container
make check
```

Open `runs/assessment_report/report.html`. Python 3.12 or later is recommended;
no third-party Python packages are required. Container execution needs the image
locally or a network connection to download it. CI checks the calculations in
Python and the preserved image when source files change.

`workflow/spec.py` defines dependencies; `workflow/` contains the calculations;
`app/` contains the interface. See [ADAPT.md](ADAPT.md), [cloud/README.md](cloud/README.md)
and [THIRD_PARTY.md](THIRD_PARTY.md) for adaptation, hosting and software sources.

Run `make html` to rebuild the self-contained page. Optional browser checks use
Playwright: `python3 scripts/check-browser.py`. They exercise offline calculations,
partial reruns, saved outputs and manual transfers. `python3 scripts/check-behaviour.py`
records the behavioural checks used in the accompanying paper.
