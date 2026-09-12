# Use the workflow structure

1. Add a job in `workflow/spec.py`: give it a name, one owner role and its input jobs.
2. Put the calculation in `workflow/models.py` or a separate module. Call it from
   `Workflow.calculate()` in `workflow/engine.py`.
3. Record every setting and code file that can change the result in
   `job_settings()` and `code_record()`.
4. Check input names, units and coverage before calculating. Return an error if
   the input is unsuitable.
5. Add a small check using fixed, shareable data. Run `make check` before adopting
   the revised version.

Run `make html` to build a self-contained browser file. The calculation must work
with the packages available in the preserved browser runtime. Other software can
be run through the Python/container interface instead.

The example runs jobs sequentially in one browser worker. An operational
orchestration service could submit the same dependency graph to approved HPC and
provide shared access to authorised colleagues. Access controls, resource requests,
storage and recovery must be implemented for that setting. Confidential data
should not be embedded in a public HTML file.
