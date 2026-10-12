# Adapting an existing fisheries calculation

Connect Malcolm Haddon's unchanged MQMF 0.1.5 `simpspm()` routine to a small
workflow, preserve its inputs, then update one growth setting. This separate
example uses historical blacklip abalone teaching data and three jobs:

```text
Original abdat → direct native prediction ─┐
Lossless CSV/JSON mapping → active prediction ─┴→ checked comparison
```

The [executable recipe](examples/mqmf-adaptation/README.md) supplies the source,
parameters and receiving checks. Imported code and data retain their exact
revision, attribution and GPL-3 licence. Catch is in tonnes; the physical CPUE
unit is undocumented. Observed CPUE keeps its original numerical scale, while
saved predictions are natural logarithms. Result plots exponentiate predictions
for comparison with observations; the saved outputs keep their declared scale.

Population parameters are supplied teaching values, not fitted estimates.
The routine calculates catchability analytically. This example does not
reconstruct the original CPUE standardisation, reproduce an author's historical
saved run, validate a stock assessment or provide management advice.

## Read the results

Open the [comparison](https://kyuhank.github.io/fisheries-workflow-demo/mqmf/cpue_summary/view.html),
then the [active prediction](https://kyuhank.github.io/fisheries-workflow-demo/mqmf/cpue_a/view.html)
and [native reference](https://kyuhank.github.io/fisheries-workflow-demo/mqmf/cpue_b/view.html).
Each report starts with the input → calculation → result and keeps detailed
settings and records below it.

## Checked execution

The [current results archive](https://kyuhank.github.io/fisheries-workflow-demo/downloads/fisheries-workflow-mqmf-1.10.0.zip)
and its [checksum](https://kyuhank.github.io/fisheries-workflow-demo/downloads/fisheries-workflow-mqmf-1.10.0.zip.sha256)
preserve these checks:

| Check | Recorded result |
| --- | --- |
| Input conversion | All 72 numerical values in 24 annual rows (1985–2008) preserved exactly. |
| Direct versus mapped input | Identical baseline predictions for all 24 years. |
| Growth update, 0.4 → 0.35 | Active prediction and comparison reran; reference output, report and record stayed byte-for-byte identical. |
| Producing records | Comparison linked the reference to Run 001 and the revised prediction to Run 002. |
| Selective versus fresh execution | All 24 predictions and 120 numerical comparison values agreed; years were checked separately. |
| Declared scale mismatch | Linear-labelled predictions were rejected before the comparison's R calculation; accepted files were preserved. |

The current checks ran in a local Linux container using the recorded SPC image.
The nine workflow steps called the original prediction function five times.
Source and
prepared-input mounts were read-only; container networking was disabled. No
optimisation was performed. The scale fixture checks a declared mismatch;
wrong-scale values incorrectly labelled as natural logs were not tested.
These recorded checks concern the preserved calculation, rather than validation
of a stock or collaboration by several human analysts.

## Inspect or repeat

Unpack the current results archive and open `study/selective/cpue_summary/report.html`.
Its `record.json` links the two producing records; the neighbouring `cpue_a/`
and `cpue_b/` folders preserve their inputs, settings and source closure.
`reports/` contains the check reports, `preflight.json` records input conversion,
and `checkpoints/baseline/` keeps the original result before the update.
Each accepted execution also provides `study-bundle.zip` and checksums.

The [earlier MQMF release](https://github.com/kyuhank/fisheries-workflow-demo/releases/tag/mqmf-adaptation-v1.0) remains unchanged.
Keep the source and results archives with the separate runtime image from
[v1.9.1](https://github.com/kyuhank/fisheries-workflow-demo/releases/tag/v1.9.1).
Follow the source README to restore the image and run the study using Docker and
a POSIX shell. The calculations then need neither a network connection nor the
original repositories. Restoration on a new computer was not tested.
