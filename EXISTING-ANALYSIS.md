# Adapting an existing fisheries calculation

This worked example connects an unchanged prediction routine from Malcolm Haddon's
MQMF 0.1.5 to the workflow. It is separate from the main 22-job synthetic example.
It shows how to preserve an existing calculation, update one setting and identify
the earlier and new results used in a comparison.

The source, inputs, settings and receiving checks are in
[the executable recipe](examples/mqmf-adaptation/README.md). The original routine
and historical blacklip abalone teaching data are included with their source
revision, attribution and GPL-3 licence. Catch is in tonnes. The physical unit of
the supplied CPUE is undocumented, so its numerical scale is retained. The
comparison distinguishes observed CPUE on that scale from natural-log predictions.

## What was checked

| Check | Result |
| --- | --- |
| Preserve the inputs | All 72 numerical values in 24 annual rows (1985–2008) survived the input conversion exactly. |
| Preserve the calculation | The wrapped and direct calls gave identical baseline predictions for all 24 years. |
| Update one setting | Changing growth from 0.4 to 0.35 reran the prediction and comparison. The reference output, report and producing record stayed byte-for-byte identical. |
| Follow the results | The updated comparison links the reference to Run 001 and the revised prediction to Run 002, with source, input and setting records for both. |
| Check the rerun decision | The selective update and fresh full execution agreed for 24 predictions and all 120 numerical comparison values; years were checked separately. |
| Stop a declared scale mismatch | A controlled input labelled as linear rather than natural-log CPUE was rejected before the comparison's R calculation ran. Previously accepted files were preserved. |

These checks ran on a Mac with Docker already installed, using the same preserved
SPC image as the main example. Source and prepared input mounts were read-only
for the four cases; container networking was disabled. No additional model was
fitted or numerical optimisation performed. The original routine estimates
catchability analytically from the supplied population parameters and observations.

The scale test converts saved predictions to linear scale in memory and declares
that scale. It checks rejection of this declared mismatch. Detection of wrong-scale
values labelled as natural-log CPUE was not tested. This example preserves one teaching calculation and its
declared inputs. It does not reproduce an author's saved historical run, reconstruct
the original CPUE standardisation, validate a stock assessment or demonstrate
collaboration by several human analysts.

## Inspect or repeat the example

The fixed release provides a complete source archive, accepted results and
execution reports:

https://github.com/kyuhank/fisheries-workflow-demo/releases/tag/mqmf-adaptation-v1.0

Open `selective/cpue_summary/report.html` in the results archive to see the annual
comparison and its producer identities. Its neighbouring `record.json` gives
the producer record paths and checksums; inspect the corresponding `cpue_a/` and
`cpue_b/` folders for their saved inputs, settings and source records. The `reports/` folder contains the four
check reports; `preflight.json` records input preservation. `checkpoints/baseline/`
keeps the original three-step result before the update. Each accepted execution
also has a `study-bundle.zip` containing its source, exact input exports, producing
records and checksums.

To calculate again, unpack the source archive and run the commands in its README.
Only a POSIX shell and Docker are needed on the host. Restore the separately
preserved SPC runtime image from the main release before running:

https://github.com/kyuhank/fisheries-workflow-demo/releases/tag/v1.9.1

Keep both archives and that runtime image. The calculations do not require the
hosted demonstration, GitHub Actions, access to the original repositories or a
network connection. Restoration on a new computer was not tested. The source
manifest remains the exact one used in the saved producing records; this guide
and the observed check results are provided alongside it.
