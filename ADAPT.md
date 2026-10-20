# Use the workflow structure

| File | Responsibility |
| --- | --- |
| `workflow/jobs.json` | Jobs, responsible analysts, input links and parallel groups. |
| `workflow/spec.py` | Load and check these declarations; select jobs and downstream paths. |
| `jobs/<job_id>/run.R` | The selected job's R entry point. |
| `jobs/<job_id>/README.md` | Inputs, settings, outputs and connected jobs. |
| `workflow/r/` | Shared GLM, RTMB surplus-production and management-trial functions. |
| `jobs/*_report/report.qmd` | Three concise Quarto reports rendered from saved results. |
| `scripts/import-public-data.py` | Verify WCPFC releases and prepare the small albacore example. |
| `workflow/extract-public.sql` | Select common cell–quarter strata for CPUE. |
| `workflow/engine.py` | Coordination, SQLite/file adapters and execution records. |
| `Makefile` | Reader commands for container runs and reproduction. |
| `workflow/Makefile` | R calculation and Quarto report recipes inside the container. |
| `workflow/r_bridge.py` | Container guard, JSON interface and process control. |
| `scripts/offline.sh` | Repeat a preserved run locally, without retrieving sources or software. |
| `app/diagram.json` | The same job graph shown as a dependency diagram. |

## Add a job

The example uses registered jobs and three pinned analysis repositories.
Extending it requires declaring the contributing code and inputs; it does not
automatically discover an arbitrary analysis or repository.

1. Define its inputs, analyst and stage in `workflow/jobs.json`, placing parents before children. Register the job in `workflow/sources.py` (`GROUPS`) and declare its calculation libraries in `JOB_LIBRARIES`. For split execution, update the corresponding component sources and source lock as well.
2. Create `jobs/<job_id>/run.R` with `calculate(context)`. Select named inputs from `context$parents` and return a named result list. Reusable R functions belong in `workflow/r/`.
3. Record settings and contributing files in `job_settings()` and `code_record()`. Check input names, units and coverage before fitting.
4. Add the node and connections to `app/diagram.json`; the build verifies these against the calculation graph. Write a concise job guide.
5. Check the change inside the declared container. Edit page sources in `app/`; `docs/` is generated from accepted source and saved calculations.

For local job or model edits, use `PAPER_SOURCE_MODE=monorepo make job JOB=cpue_a`
(or `PAPER_SOURCE_MODE=monorepo make run` for all jobs). The default route runs
the component revisions in `source-lock.template.json`; update those repositories
and pins when adopting the change.

The coordinator reads the declarations and checks saved inputs to select ready
jobs. `workflow/Makefile` calls their R entry points. The coordinator then records
the outputs and releases dependent jobs. Independent jobs can run together;
declared peer groups finish before later stages advance. Both demo views show
these job connections.

A Live request uses the existing [hosted service](cloud/README.md): it starts
`.github/workflows/live.yml`, pulls the recorded image and calls `make inside-live`
there. `cloud/run.py` retrieves the request and runs the same coordinator. The job
configuration defines the calculations; the service requires a separate deployment.

See [GitHub Actions](https://docs.github.com/en/actions/get-started/understand-github-actions)
for workflows and runners, and the
[Docker overview](https://docs.docker.com/get-started/docker-overview/)
for images and containers.

## Separate analyst repositories

The default execution uses three exact source pins in [source-lock.template.json](source-lock.template.json): preparation/CPUE owns eight jobs, assessment owns eight (including `prepare_a`/`prepare_b`), and MSE owns six.

`scripts/hydrate-sources.py` checks the selected Git commits and clean source bytes,
then assembles an offline snapshot. Hosted Actions hydrate before entering the
preserved container. `make run`, `make check` and `make html` assemble and verify
the pinned sources before entering the container; source checks stop execution
if the required assembly is missing or inconsistent.

The coordinator owns shared `common.R`, the driver, input graph, SQLite adapters, source resolver, reports and software image. CPUE owns `R/cpue.R`, assessment owns `R/assessment.R`, and MSE owns `R/mse.R`. The exact per-job library declarations in `workflow/sources.py` control both loading and fingerprints. MSE preparation also loads assessment's `surplus_path`. A library revision invalidates jobs loading those bytes and their descendants; changing unrelated documentation or a component commit alone does not invalidate unchanged dependencies.

`workflow/contracts.py` checks relative CPUE indices, annual catch in tonnes, years and admissible values before assessment preparation, and the four assessment cases and required fields before MSE preparation. Records distinguish component `analysis_source` and `code_sources` from the coordinator's `source`/`execution`; inputs retain producer runs, source pins, signatures and artifact checksums. Downloaded runs preserve the component sources, source lock and origin manifest for network-disabled reproduction.

The [repository map](examples/analyst-repositories.yaml) is a reader guide; the
executable registered pins are the JSON lock and `workflow/jobs.json`. A single
host coordinates these jobs; repository separation does not establish multiple
human analysts or operational fisheries use.

## Change the example

The growth control maps to `growth_rate_2`; the second assessment cases record
this fixed `r` value. Changing it invalidates those fits and their descendants.
The MSE buffer maps to `mse_buffer`; only the Buffered rule uses it. A buffer
revision retains the prepared cases, common errors and other rules. The summary
checks that every rule uses the same operating models, assumptions and recorded
random streams before producing a comparison.

The default example uses the [preserved public releases](data/public/README.md).
`scripts/import-public-data.py` checks archive and member hashes, converts the
declared units and writes the source projection. The SQL selects common observed
strata; the R model standardises catch per effort on a fixed prediction grid.
Keep source rows, transformations, units and sampling support explicit when
substituting data. The annual stock catch series is a separate input.
`scripts/seed-public-data.py` writes a PostgreSQL seed for the same snapshot.

The earlier synthetic fixture remains available with `PAPER_DATA_MODE=synthetic`.
Its generator and SQLite importer are retained for regression checks. Label any
new simulations and preserve their generating code, seed and scenario.

If software requirements change, build and check a new image version before
updating the immutable digest in the workflow. The browser and downloaded HTML
display saved results; calculations run in the container. Code, inputs and results
are preserved separately from the software image. Keep a copy of the built image
with each release; [OFFLINE.md](OFFLINE.md) gives the save and restoration commands.

## Maintain a release

Edit source files, not generated pages in `docs/`. Check changed calculations
and their input contracts in the pinned container before updating a component
source pin. The existing calculation, interface and server checks can be run
through the repository workflows; a local preserved run can be checked without
the hosting service.

Keep earlier release archives and image copies. A new release should retain its
own source pins, input snapshots, settings, outputs, execution records and
checksums. `scripts/release.py` adds local reading and execution tools to the
saved run without replacing its recorded analysis sources. Support-tool versions
can therefore differ from the saved analysis version.

## Numerical comparisons

`verify.py` compares output values at relative tolerance 1e-6 or absolute tolerance
1e-9. Assessment log-index residuals retain relative tolerance 1e-6 with absolute
tolerance 1e-8 after checking them against the observed and fitted indices. Two
near-zero assessment gradient diagnostics have magnitude and difference caps of
1e-7, conditional on matching successful fit diagnostics. These are comparison policies, not model-accuracy
guarantees. Summary and report copies must match their own source assessments
before the exceptions apply. Other values retain the general tolerances.
