# Use the workflow structure

| File | Responsibility |
| --- | --- |
| `workflow/jobs.json` | Jobs, responsible analysts, input links and parallel groups. |
| `workflow/spec.py` | Load and check these declarations; select jobs and downstream paths. |
| `jobs/<job_id>/run.R` | The selected job's R entry point. |
| `jobs/<job_id>/README.md` | Inputs, settings, outputs and connected jobs. |
| `workflow/r/` | Shared GLM, RTMB surplus-production and management-trial functions. |
| `jobs/*_report/report.qmd` | Three concise Quarto reports rendered from saved results. |
| `scripts/generate-data.R` | Declared synthetic catch history and observations. |
| `workflow/engine.py` | Coordination, SQLite/file adapters and execution records. |
| `Makefile` | Reader commands for container runs and reproduction. |
| `workflow/Makefile` | R calculation and Quarto report recipes inside the container. |
| `workflow/r_bridge.py` | Container guard, JSON interface and process control. |
| `app/diagram.json` | The same job graph shown as a dependency diagram. |

## Add a job

1. Define its inputs, analyst and stage in `workflow/jobs.json`, placing parents before children.
2. Create `jobs/<job_id>/run.R` with `calculate(context)`. Select named inputs from `context$parents` and return a named result list. Reusable R functions belong in `workflow/r/`.
3. Record settings and contributing files in `job_settings()` and `code_record()`. Check input names, units and coverage before fitting.
4. Add the node and connections to `app/diagram.json`; the build verifies these against the calculation graph. Write a concise job guide.
5. Check the change inside the declared container. Edit page sources in `app/`; `docs/` is generated from accepted source and saved calculations.

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

The [job guide](jobs/README.md#separate-repositories) follows a concrete CPUE →
preparation → assessment handover. The
[illustrative catalogue](examples/analyst-repositories.yaml) gives each analyst's
repository a source commit and identifies the shared code, container and artifacts.
Its values are placeholders; the current coordinator does not read this YAML.
[`workflow/jobs.json`](workflow/jobs.json) remains the executable configuration.

A service would need to retrieve the pinned source and shared dependencies,
transfer artifacts and verify their checksums, check fields, units and years,
and assemble each job's `context`. It would then run the job through an approved
execution route and preserve outputs and records. Repository access, artifact
storage and these adapters require implementation and validation.

## Change the example

The growth control maps to `growth_rate_2`; the second assessment cases record
this fixed `r` value. Changing it invalidates those fits and their descendants.
The MSE buffer maps to `mse_buffer`; only the Buffered rule uses it. A buffer
revision retains the prepared cases, common errors and other rules. The summary
checks that every rule uses the same operating models, assumptions and recorded
random streams before producing a comparison.

Generate synthetic data with `scripts/generate-data.R` inside the pinned image,
then use `scripts/import-r-data.py` to store its JSON as SQLite and a submission.
Preserve the JSON, generating source, seed and scenario. A hosted PostgreSQL copy
must use those same generated observations and annual catches.

If software requirements change, build and check a new image version before
updating the immutable digest in the workflow. The browser and downloaded HTML
display saved results; calculations run in the container. Code, inputs and results
are preserved separately from the software image.

## Numerical comparisons

`verify.py` compares output values at relative tolerance 1e-6 or absolute tolerance
1e-9. Assessment log-index residuals retain relative tolerance 1e-6 with absolute
tolerance 1e-8 after checking them against the observed and fitted indices. Two
near-zero assessment gradient diagnostics have magnitude and difference caps of
1e-7, conditional on matching successful fit diagnostics. These are comparison policies, not model-accuracy
guarantees. Summary and report copies must match their own source assessments
before the exceptions apply. Other values retain the general tolerances.
