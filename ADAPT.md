# Use the workflow structure

| File | Responsibility |
| --- | --- |
| `workflow/spec.py` | Jobs, owners, dependencies and parallel groups. |
| `workflow/models.py` | The example analyses. |
| `workflow/mse.py` | Assessment-conditioned stocks, management trials and their comparison. |
| `workflow/engine.py` | Execution, input checks, saved results and run records. |
| `app/diagram.json` | Diagram nodes, positions and connections. |
| `app/app.js` | Controls, progress and workflow views. |

1. Add a job in `workflow/spec.py`: give it a name, one owner role and its input jobs.
   List parents before children in `JOBS`. Include the job in `STAGES`, in a group
   after its parents; independent jobs can share a group.
2. Put the calculation in `workflow/models.py` or a separate module. Call it from
   `Workflow.calculate()` in `workflow/engine.py`.
3. Record every setting and code file that can change the result in
   `job_settings()` and `code_record()`.
4. Check input names, units and coverage before calculating. Return an error if
   the input is unsuitable.
5. Add its node and input connections to `app/diagram.json`. The page build checks
   that the diagram matches the workflow.
6. Add a small check using fixed, shareable data. Run `make check` before adopting
   the revised version.

Run `make html` to build the website in `docs/index.html` and the self-contained
download in `docs/offline.html`. This also reruns the default synthetic example
to generate the saved reports. Edit interface sources in `app/`; `docs/` is generated.
The website loads its `runtime-*.json` file only
when Offline run is selected. The calculation must work
with the packages available in the preserved browser runtime. Other software can
be run through the Python/container interface instead.

The hosted container runs independent jobs in separate processes and waits for the
whole peer group before its dependent stages advance. Independent reporting can
continue during an assessment file handover. The offline browser uses one Python
worker with the same barriers. Define peer groups and file-transfer boundaries
in `workflow/spec.py`; calculation input dependencies remain separate. An operational
orchestration service could submit the same dependency graph to approved HPC and
provide shared access to authorised colleagues. Access controls, resource requests,
storage and recovery must be implemented for that setting. Confidential data
should not be embedded in a public HTML file.

The **MSE catch buffer** control maps to `mse_buffer` in `workflow/spec.py` defaults
and downloaded `settings.json`. Only `mse_buffered` records that value as its
`buffer` setting. `workflow/mse.py:simulate()` applies it and preserves it in the
MP output and comparison. Allowed choices are 0.6, 0.8 and 1.0; the annual advice
change limit stays at 0.15. Older settings files without the control use 0.8.
The UI, cloud planner and hosted request allowlist must agree with the Python
settings validation; redeploy `paper-api` when that allowlist changes.

To change **Prepare MSE**, edit `prepare()` and `ASSUMPTIONS` in `workflow/mse.py`.
`CASES` selects the four fitted assessment inputs; `prepare()` reconstructs their
future starting numbers and derives reference catches and indices from the last
three years. `ASSUMPTIONS` defines the seed, horizon, trial count, recruitment
scenarios and observation errors. Fixed biology is in `workflow/age_model.py`.
These common trial conditions are separate from the Buffered rule's catch
fraction, so changing that fraction retains the prepared operating models and
the other MPs. Adapting the common assumptions requires rerunning preparation
and all management trials.
