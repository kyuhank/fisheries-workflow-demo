# Fisheries workflow demonstration

[Open the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Orchestration tool](https://kyuhank.github.io/fisheries-workflow-demo/#orchestration) · [Download](https://github.com/kyuhank/fisheries-workflow-demo/releases)

Follow a change in fishing records through CPUE analysis, stock assessment and
management strategy evaluation (MSE). Inspect the inputs, code and software behind
each result, then rerun the affected analyses. Synthetic data and simple models
make the connections easy to explore; the results provide no advice for a real fishery.

## Run the demo

| Mode | What happens |
| --- | --- |
| **Live run** | GitHub Actions retrieves the recorded Docker image on a remote computer and runs the R jobs and reports inside its container. No login is needed. |
| **View example** | Explore saved outputs and execution records without running the analyses. |

[GitHub Actions](https://docs.github.com/en/actions/get-started/understand-github-actions)
provides the remote execution service. The
[container image](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-an-image/)
packages the software needed by the R scripts and reports, so runs use the same
recorded software environment.

The **Workflow diagram** shows the inputs passed between analyses. The
**Orchestration tool** uses these connections to start jobs when their inputs are
ready. Its task view groups related jobs and shows progress and execution records.

1. Choose **Live run** and complete **Run full workflow**.
2. Change **CPUE A records**, **Growth-rate setting 2** or **MSE catch buffer**.
3. Select **Update workflow**. Affected jobs rerun; unchanged results keep their records.
4. Under **Tasks**, select a job and open **Record** to follow its inputs and versions.

**Run** executes one selected job after preparing its required inputs.
**Dependencies** shows connected jobs; **Reproduce & compare** checks a result.
**Manual handover** pauses a transfer until **Confirm file transfer** is selected,
while independent jobs continue. No file upload is required in this example.

## Explore the code

Start with [jobs/](jobs/README.md), which lists all 22 jobs in execution order.
Each folder contains an R entry point and a short guide to its inputs, settings
and outputs. [CPUE A](jobs/cpue_a/README.md), for example, reads fishing records,
produces an index and supplies [assessment preparation A](jobs/prepare_a/README.md).
The demo's **Record** view links to the corresponding job folder.

The jobs are kept in one repository so readers can inspect and download the
example together. The [repository guide](jobs/README.md#separate-repositories)
shows the files analysts would exchange if they maintained their tasks in
separate repositories. [ADAPT.md](ADAPT.md) explains the configuration, shared
R functions and Make recipes.

## Download and repeat

Download `fisheries-workflow.html` from a release to inspect saved results offline.
If live execution is unavailable, the web interface offers **View example**.

**Download this run** saves the code, exact synthetic inputs, settings, records
and outputs. Save it before live results expire, about ten minutes after the last
run activity. The archive's `REPRODUCE.txt` gives the recorded image, Docker
commands and comparison instructions. A single-job download repeats that job;
other saved results retain their original records.

All calculations and reports run inside the
[execution image](https://github.com/PacificCommunity/ofp-sam-docker-images/pkgs/container/fisheries-workflow),
which supplies R, RTMB, Quarto and the other required software. Docker and Make
are required on the host; ARM computers need AMD64 emulation. After the image is
pulled, a downloaded run can be repeated without network access.

From the repository root:

```sh
make run                 # full workflow
make job JOB=cpue_a       # one job and its required inputs
```

In a run download, follow `REPRODUCE.txt` and use `make reproduce` and
`make compare`. See [cloud/README.md](cloud/README.md) for hosting and
[THIRD_PARTY.md](THIRD_PARTY.md) for software sources and licences.
