# Use the workflow structure

| File | Responsibility |
| --- | --- |
| `workflow/spec.py` | Jobs, responsible analysts, dependencies and parallel groups. |
| `jobs/<job_id>/run.R` | The selected job's R entry point. |
| `jobs/<job_id>/README.md` | Inputs, settings, outputs and connected jobs. |
| `workflow/r/` | Shared GLM, RTMB surplus-production and management-trial functions. |
| `jobs/*_report/report.qmd` | Three concise Quarto reports rendered from saved results. |
| `scripts/generate-data.R` | Declared synthetic catch history and observations. |
| `workflow/engine.py` | Coordination, SQLite/file adapters and execution records. |
| `workflow/r_bridge.py` | Container guard and Rscript job interface. |
| `app/diagram.json` | The same job graph shown as a dependency diagram. |

## Add a job

1. Define its inputs, analyst and stage in `workflow/spec.py`, placing parents before children.
2. Create `jobs/<job_id>/run.R` with `calculate(context)`. Select named inputs from `context$parents` and return a named result list. Reusable R functions belong in `workflow/r/`.
3. Record settings and contributing files in `job_settings()` and `code_record()`. Check input names, units and coverage before fitting.
4. Add the node and connections to `app/diagram.json`; the build verifies these against the calculation graph. Write a concise job guide.
5. Check the change inside the declared container. Edit page sources in `app/`; `docs/` is generated from accepted source and saved calculations.

The hosted coordinator runs independent jobs in separate container processes and
waits for required peer outputs before later stages advance. The orchestration
view groups these jobs by task; the diagram maps their required inputs. Both
views describe the same execution.

## Separate analyst repositories

The demo keeps all jobs in one repository to make inspection and downloads easy.
An assessment programme could maintain each analyst's task in its own repository.
The coordinator would retrieve the selected source version for each job and pass
identified outputs between repositories. Analysts would agree on input products,
units, years and checks. Records would retain the contributing source versions,
container digests and upstream runs. Repository separation alone does not supply
these connections or the programme's access controls.

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

The container includes all required R packages and Quarto. If requirements change,
build and check a new image version before updating the immutable digest in the
workflow. No new analysis runs in the browser; the downloaded HTML is a saved
result reader. Code, inputs and results remain separate from the software image.
