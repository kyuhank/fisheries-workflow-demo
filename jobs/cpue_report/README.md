# CPUE report (`cpue_report`)

Render the saved CPUE comparison as a Quarto report. The report reads the result and run record without refitting the GLMs.

Analyst role: CPUE analyst. [run.R](run.R) supplies the saved results; [report.qmd](report.qmd) renders the report.

## Inputs and settings

Previous jobs: [Compare CPUE results (`cpue_summary`)](../cpue_summary/README.md)

Input files: `runs/cpue_summary/output.json` and the report job's saved run record.

Saved settings: No job-specific settings (`{}`).

## Run in the container

Inside the declared container, from the repository root:

```sh
make inside-job JOB=cpue_report
```

The coordinator refreshes required inputs and calls this job through
`workflow/Makefile`. `OUTPUT=DIR` changes the default `runs` directory;
`SETTINGS=FILE` supplies JSON settings. The run record identifies the image and
software versions used.

## Outputs and downstream jobs

- `runs/cpue_report/output.json`: the R calculation result.
- `runs/cpue_report/report.html`: the Quarto report from [report.qmd](report.qmd).
- `runs/cpue_report/record.json`: inputs, settings, R source hashes, actual container identity and software used.

Downstream jobs: None.

Saved example: [Report](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/report.html) · [Output JSON](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/output.json) · [Run record](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/record.json).
