This separate, executable study adopts Malcolm Haddon's existing MQMF `simpspm()` routine at the recorded source revision. It preserves the original coordinator's scheduler and reuse rules, adds three study wrappers, and compares two new local calls of the same unchanged external function. See [STUDY.md](STUDY.md) for the complete recipe and limits.

Run from this folder:

```sh
sh study.sh prepare
sh study.sh baseline
sh study.sh update
sh study.sh fresh
sh study.sh wrong-scale
```

Alternatively, `sh study.sh all` performs the same preparation and four cases sequentially. `sh study.sh check` checks the frozen source and already local image without calculations. Execution needs POSIX shell and Docker on the host; Python, Make, R and jsonlite run inside the already preserved SPC image. No packages, sources or images are fetched by these commands. The study supports the preserved v1.9.1 image restored from its separate archive, including restoration without registry `RepoDigests`.

Results default to `../study-runs`. Set `STUDY_OUTPUT=/absolute/results/folder` to choose another location. Keep the source folder read-only. Cases cannot be retried against the same ledger, and the runner caps the entire case set at nine step attempts, five external routine calls and 1,200 seconds. Each R subprocess is bounded at 60 seconds. Source and parameter bytes are frozen together; only selection of the active parameter file changes during the update.

If Docker lacks the image, restore your already verified v1.9.1 runtime archive manually with `docker image load --input /absolute/path/fisheries-workflow-runtime.tar.gz`, following its preserved receipt/guide. Then `sh study.sh check` verifies the restored config ID and ordered layers before any study calculation. The source bundle contains no runtime image.

The combined study is GPL-3.0-only. Original coordinator files retain their MIT notice in [notices/LICENSE-coordinator-MIT.txt](notices/LICENSE-coordinator-MIT.txt). Imported MQMF source and data retain their GPL-3 declaration, attribution and exact bytes. See [THIRD_PARTY.md](THIRD_PARTY.md). This study leaves the original paper, public demonstration, 22-job graph, model sources, releases and SPC image unchanged.
