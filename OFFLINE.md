# Repeat and preserve the analyses

Keep the offline ZIP and the execution-image archive together. The ZIP contains
the saved run's exact synthetic inputs, settings, source snapshots, outputs and
execution records. The image contains its R packages, Python, Make and Quarto.
The offline tools are supplied with these older analysis sources so that a new
tool release does not replace the code used to produce the saved results.

## Read the example

Unpack `fisheries-workflow-offline-1.9.1.zip` and open `START-HERE.html`. Follow
the links from a result to its input records, job script and calculation library.
`code.html` displays the preserved sources. These pages use local files and need
no login or internet connection. The interactive HTML displays saved results;
new calculations use the commands below.

## Restore the software

Install Docker and start its engine. Use a POSIX shell, available on Linux and
macOS or through WSL on Windows. The image is for Linux AMD64; ARM hosts need
Docker's AMD64 emulation. Docker and a compatible operating system must remain
available even when the saved software is kept.

Place `fisheries-workflow-runtime.tar.gz`, `runtime-archive.json` and
`SHA256SUMS.json` in a folder named `runtime` next to the extracted analysis
folder. From the analysis folder:

```sh
sh scripts/preserve-runtime.sh load ../runtime
```

This loads your preserved archive, then checks its checksum and the restored
image's configuration and software layers before running an analysis. Use an
archive from a trusted copy of the release. A restored image can lose its registry
digest label; the tools therefore check the recorded local image identity and
layers before launching it. They record that identity alongside the original
SPC registry reference. The checks identify the preserved software, not the
scientific validity of its results.

If the recorded image is already present, loading the archive is unnecessary.
The offline runner checks it before use and stops if it is missing. It never
pulls an image or retrieves source repositories.

## Repeat and compare

From the extracted analysis folder:

```sh
sh scripts/offline.sh reproduce
sh scripts/offline.sh compare
```

The first command repeats the saved workflow using its recorded settings. The
second compares the numerical results with `reference/`, using the unchanged
comparison rules in `verify.py`. New reports and records are in `offline-runs/`.
The calculations run with network access disabled; the source folder is mounted
read-only. The runner verifies packaged files and the component source snapshots
before starting an analysis.

To run one job and prepare its required inputs:

```sh
sh scripts/offline.sh job cpue_a
```

For a single-job run download, use the job named in `REPRODUCE.txt`:

```sh
sh scripts/offline.sh reproduce cpue_a
sh scripts/offline.sh compare cpue_a
```

These commands compare that job only. Other saved results keep their original
records. An earlier download without the offline tools retains its original
instructions and requires the host tools listed there.

## Continue an analysis

`sh scripts/offline.sh run` starts the workflow with the example's default
settings. Use the same output folder to continue from its saved state; the
coordinator checks which results require recalculation. Keep original downloads
and write changes into a separate working copy. For code or input changes, use
the development route in [ADAPT.md](ADAPT.md): the preservation runner deliberately
rejects changes to packaged files.

## Keep an independent copy

If you already have the recorded image, save it for later use:

```sh
sh scripts/preserve-runtime.sh ../runtime
sh scripts/preserve-runtime.sh verify ../runtime
```

Keep the ZIP, runtime files, licences and checksums on storage independent of
the GitHub account. Their contents can be copied to a code or data archive;
GitHub release links alone do not provide an independent deposit. Each software
component retains its own licence, as described in [THIRD_PARTY.md](THIRD_PARTY.md).
Preserved copies do not require this website or the original image registry to
remain online. They still require a Docker-compatible computer.
