# Fisheries workflow demonstration

[Open the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Code by job](jobs/README.md) · [Preserved releases](https://github.com/kyuhank/fisheries-workflow-demo/releases)

Follow public catch and effort data through CPUE standardisation, stock
assessment and management strategy evaluation (MSE). Change an input or setting
to see which analyses need to run again and which results can be retained.
Each result links to its inputs, code, settings and software. The models
demonstrate the workflow and provide no advice for South Pacific albacore.

## Use the demo

**View example** opens the saved results; **Live run** executes the R jobs and
Quarto PDFs on GitHub Actions. CPUE plots show nominal and standardised rates
together. **View** opens a job's PDF; **Inputs & versions** traces its sources.
PDFs read saved numerical results. The three report jobs contain the methods
and checks.

**Run full workflow** starts with data through 2021. Selecting 2022 adds the
final available year. After a setting changes, **Update workflow** reruns the
affected analyses and retains unchanged results with their original records.
**Run** prepares the selected job's required inputs and stops at that job.

**Manual handover** pauses receiving jobs until **Confirm file transfer**;
other ready jobs continue. **Reproduce & compare** repeats the recorded
workflow and compares the selected result. **Download this run** preserves
source, inputs, records and outputs before live results expire after about
ten minutes.

## Data and methods

The default input contains released WCPFC longline records for the FJ fleet,
2000–2022, in six fixed cell–quarter strata. A row aggregates a fleet, year,
five-degree cell and quarter; it is not an individual fishing set. Vessel IDs
are unavailable. `hooks` is reported effort (`HHOOKS × 100`) and `catch_n` is
albacore catch in numbers (`ALB_N`). The legacy `set_id` field identifies an
aggregate source row. See [data/public-source.json](data/public-source.json) for
the supplied rows and source metadata, and [data/public-data.json](data/public-data.json)
for the extraction record.

Recorded SQL extracts the CPUE rows from a SQLite snapshot. Annual South Pacific
albacore catches, in tonnes, come from a separate yearbook series; they are not
a sum of the selected fleet's catch numbers.

CPUE A fits a quasipoisson GLM with year and cell–quarter effects and a
`log(hooks / 1000)` offset. It predicts fish per 1,000 hooks in each stratum and
averages those predictions with equal fixed weights. CPUE B uses year and quarter
effects. Both indices are divided by their first-year value. The outputs preserve
nominal and standardised CPUE, prediction support, weights and model checks.
Quarter effects partly confound spatial differences on this support.
These selected released strata do not represent the whole stock; the example
supplies no confidence intervals. The selected Fiji fleet index is not a validated
stock-wide abundance measure. Synthetic vessel records remain available as
regression fixtures.

The four Schaefer assessment cases combine these indices with fixed growth
assumptions. Seeded MSE trials compare constant catch, an index rule and a
buffered rule under shared simulated conditions. Case differences and trial
fractions describe those assumptions, rather than calibrated uncertainty or risk.
All rules share a simulator catch cap of 40% of true starting biomass; the
low-biomass results are conditional on that guardrail.

## Run or adapt the code

The [22 job guides](jobs/README.md) show each input → method → output path.
The coordinator loads code from [pinned component repositories](jobs/README.md#separate-repositories)
and records each producing run and file checksum.

From a checkout, with Docker, Make, Python 3 and Git available:

```sh
make run                 # all jobs
make job JOB=cpue_a       # CPUE A and required inputs
```

To use another fishery, start with the source mapping and saved SQL, then
choose the CPUE covariates and prediction support explicitly. Review annual
catch units, assessment assumptions and the receiving file contracts before
running later jobs. [ADAPT.md](ADAPT.md) describes the connections and source
pins; [cloud/README.md](cloud/README.md) covers hosting.

For an existing-analysis example, the [MQMF adaptation](EXISTING-ANALYSIS.md)
preserves an abalone prediction routine and compares direct and mapped inputs.

## Preserve a run

Keep a downloaded run and its recorded execution image together. Follow the
bundle's `REPRODUCE.txt` to repeat its declared scope. The
[public-data example](https://kyuhank.github.io/fisheries-workflow-demo/downloads/fisheries-workflow-offline-1.11.5.zip)
includes local result and code pages, source archives, extraction SQL and all
22 reference outputs; its
[checksum](https://kyuhank.github.io/fisheries-workflow-demo/downloads/fisheries-workflow-offline-1.11.5.zip.sha256)
identifies the download. Open `START-HERE.html`, then follow `OFFLINE.md`.
The archived
[v1.9.1 release](https://github.com/kyuhank/fisheries-workflow-demo/releases/tag/v1.9.1)
preserves the earlier synthetic example and its separate image archive.
[OFFLINE.md](OFFLINE.md) explains restoration and offline comparison; current
source changes do not alter that preserved release.

Software attribution and licences are in [THIRD_PARTY.md](THIRD_PARTY.md).
