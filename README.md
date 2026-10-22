# Fisheries workflow demonstration

[Open the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Offline download](https://kyuhank.github.io/fisheries-workflow-demo/downloads/fisheries-workflow-offline-1.12.0.zip)

Follow public catch and effort data through CPUE standardisation, assessment and
management strategy evaluation. R coordinates the jobs; each analysis repository
owns its Makefile and R calculations. Jobs can use different immutable Docker
images. Changing one input, setting or job image reruns its dependent branch;
retained results keep their original producing records.

With R (`jsonlite`, `digest`, `DBI`, `RSQLite`), Make, Docker, Git and a POSIX shell:

```sh
make run                    # all jobs; results in runs/
make job JOB=cpue_a          # one job and required inputs
make check                  # declared source and interface checks
```

From an extracted saved-run download, after restoring its images:

```sh
make reproduce              # repeat its saved scope and compare numerical outputs
```

| Read | Location |
| --- | --- |
| Job graph and input connections | [22 job guides](jobs/README.md), [declarations](workflow/jobs.json) |
| R calculations and their own Make commands | [CPUE](https://github.com/kyuhank/fisheries-workflow-cpue-demo), [assessment](https://github.com/kyuhank/fisheries-workflow-assessment-demo), [MSE](https://github.com/kyuhank/fisheries-workflow-mse-demo) |
| Saved results and producing records | [result browser](https://kyuhank.github.io/fisheries-workflow-demo/example/); locally `runs/<job>/output.json`, `record.json` |
| Reports | [CPUE](https://kyuhank.github.io/fisheries-workflow-demo/example/cpue_report/report.pdf), [assessment](https://kyuhank.github.io/fisheries-workflow-demo/example/assessment_report/report.pdf), [MSE](https://kyuhank.github.io/fisheries-workflow-demo/example/mse_report/report.pdf) |
| Adapt or preserve a run | [ADAPT.md](ADAPT.md), [OFFLINE.md](OFFLINE.md) |

The browser opens saved Quarto PDFs. Live requests use the configured GitHub
Actions service; manual handovers pause receiving jobs while other ready jobs
continue. Download a completed run to retain its source, inputs, software
identities, outputs and records. Preserve the separate image archives too.
`make portable ARCHIVE=release.zip OUTPUT=portable-workflow PACKAGE_SOURCES=/path/to/R-sources`
collects a completed release, its local images and matching host R package sources
for independent storage or sharing. See [offline preparation](OFFLINE.md#prepare-an-offline-share).

The example uses released WCPFC/SPC Fiji fleet–quarter–5° cell aggregates,
2000–2022. Rows are not individual sets; vessel IDs are unavailable. Hooks are
`HHOOKS × 100`, catch numbers are `ALB_N`, and annual South Pacific stock catch
is a separate series in tonnes. Masked cells are excluded; their zeros are not
observed zero catches. CPUE uses six fixed cell–quarter strata; this small fleet
index is not validated as stock-wide abundance. Fixed-growth Schaefer cases and
seeded management trials illustrate the workflow and provide no stock advice.
Keep the [data notices](data/public/README.md) and [software licences](THIRD_PARTY.md).
