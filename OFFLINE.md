# Repeat a saved run

## Local run

The local runner performs the same jobs as Live run, using your computer's Docker
engine. It supports the same data-year, growth and catch-buffer settings, job or
workflow execution, and manual input transfers. It uses no GitHub or Supabase
service. The current public demo remains available separately.

Install R, Make and Docker, then prepare the five host R packages once while online:

```sh
Rscript --vanilla scripts/setup-host.R --local
```

After unpacking the saved source ZIP and restoring its saved images, start:

```sh
sh scripts/local.sh --port 8765 --workspace /absolute/local-runs
```

Open `http://127.0.0.1:8765`. Change settings and run jobs from the same diagram.
The workspace holds new results; the archived source and reference results stay
available for comparison. Stop the local service with Ctrl+C. Linux or a POSIX
environment such as WSL is required; the supplied images use Linux AMD64.
The prepared package and images can be kept on local storage and shared together
through a research archive. Starting this local runner requires no internet access.

## Prepare an offline share

With a completed release ZIP, its recorded images available in Docker and a cache
of the installed host packages' source archives, run:

```sh
make portable ARCHIVE=/path/to/release.zip OUTPUT=/path/to/new-share PACKAGE_SOURCES=/path/to/R-sources
```

The source cache must contain the exact installed versions and their dependencies
as `package_version.tar.gz`. Preparation checks these identities, preserves the
images and writes checksums. It retrieves nothing from CRAN, GitHub or a registry.
Choose a new output directory; its `workflow/` retains the release and manifest,
with image archives and host package sources alongside it.

On another computer with R development headers, Make, Docker and a suitable C/C++
compiler, use the prepared directory without online services:

```sh
Rscript offline-host-install.R --library /absolute/offline-R-library
R_LIBS_USER=/absolute/offline-R-library Rscript workflow/scripts/offline.R archive-load runtime-copy
R_LIBS_USER=/absolute/offline-R-library make -C workflow local
```

Use `make -C workflow reproduce` with the same `R_LIBS_USER` to compare the archived
calculation. Keep the directory's source, reference results, receipts and checksums
together when copying it to independent storage or a research archive. New local
results retain their own producing records in a separate workspace.

## Repeat the archived calculation

Unpack the offline ZIP and open `START-HERE.html`. Its table links each result
to the PDF, numerical output, producing record and R source. `code.html` lists
the preserved coordinator and component sources. Reading uses local files.

The ZIP preserves source, inputs, settings, reference outputs and runtime
identities. Docker image bytes are separate: keep the ZIP and an archive of
every image in `runtime-catalogue.json` on independent storage.

Use R with `jsonlite`, `digest`, `DBI` and `RSQLite`, Make, Docker and a POSIX
shell (Linux, macOS or Windows with WSL). The supplied images use Linux AMD64;
ARM hosts require compatible Docker emulation.

From the extracted folder, restore your saved images:

```sh
sh scripts/preserve-runtime.sh load /absolute/runtime-copy
make reproduce
```

The loader checks archive checksums before loading, then verifies every restored
image's config ID, platform and ordered software layers. Reproduction verifies
the packaged file manifest, uses the preserved source snapshots and recorded
settings, disables image pulls and container networking, and compares new
numerical outputs with `reference/`. Results go to `offline-runs/`.
A restored image need not retain its registry digest label: its exact config and
layers must still match the preserved catalogue.

A single-job download repeats its declared job by default. To select a saved job
explicitly, or compare an existing reproduction:

```sh
make reproduce JOB=cpue_a
Rscript --vanilla scripts/offline.R compare cpue_a
```

Its required inputs are checked or prepared; unrelated saved results retain
their producing records. Set `PAPER_OFFLINE_OUTPUT=/absolute/results` to choose
a separate result folder. Keep `reference/` unchanged.

`comparison-policy.json` declares relative tolerance `1e-8` and absolute tolerance
`1e-9`. Assessment log residuals permit absolute `1e-8` after consistency checks;
near-zero gradients have magnitude and difference caps of `1e-7` conditional on
matching successful fit diagnostics. Copied assessment fields must equal their
own source output. JSON structure and nonnumerical values must match. These are
reproduction comparison rules, not model-accuracy guarantees.

If all recorded images are available locally, preserve them before archiving:

```sh
sh scripts/preserve-runtime.sh save /absolute/runtime-copy
sh scripts/preserve-runtime.sh verify /absolute/runtime-copy
```

This writes one `runtime-images/<config>.tar` per distinct image, archive
checksums and a catalogue receipt. Mixed images used by retained jobs are
included. Save, verify and load never pull software or retrieve source.

For development, work in a separate source checkout and follow [ADAPT.md](ADAPT.md).
The preservation runner rejects changes to packaged files. Historical releases
keep their original execution tools and instructions.
