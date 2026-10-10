# Fisheries workflow demonstration

[Open the demo](https://kyuhank.github.io/fisheries-workflow-demo/) · [Orchestration tool](https://kyuhank.github.io/fisheries-workflow-demo/#orchestration) · [Download](https://github.com/kyuhank/fisheries-workflow-demo/releases)

Reproduce earlier analyses before building on them or reviewing the basis of
advice. Follow catch per unit effort (CPUE) indices through stock assessment into
management strategy evaluation (MSE), tracing the inputs, code and software
behind each result. The synthetic data and simplified models illustrate the
process; they provide no advice for a real fishery.

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

1. Choose **View example** to explore the 22 completed jobs.
2. Under **Tasks**, select an analysis. Open **Output** to read its result or
   **Record** to follow the exact earlier results it used.
3. Choose **Live run**, then **Run full workflow** to repeat the analyses.
4. Change **CPUE A records**, **Growth rate setting 2** or **MSE catch buffer**,
   then choose **Update workflow**. Affected jobs rerun; unchanged results keep
   their records.

**Run** executes one selected job after preparing its required inputs.
**Dependencies** shows inputs and later analyses. **Reproduce & compare** repeats
the workflow with recorded settings and compares the selected result with its
saved reference.
**Manual handover** pauses a transfer until **Confirm file transfer** is selected,
while independent jobs continue. No file upload is required in this example.

## Explore the code

Start with [jobs/](jobs/README.md), which lists all 22 jobs in execution order.
Each folder contains an R entry point and a short guide to its inputs, settings
and outputs. [CPUE A](jobs/cpue_a/README.md), for example, reads catch and effort records,
produces an index and supplies [assessment preparation A](jobs/prepare_a/README.md).
The demo's **Record** view links to the corresponding job folder. For the saved example,
[read reports alongside their exact code](https://kyuhank.github.io/fisheries-workflow-demo/offline-guide/START-HERE.html).

The coordinator loads preparation/CPUE, assessment and MSE code from three
[exactly pinned repositories](jobs/README.md#separate-repositories). Their source
bytes, input producer records and the identity of the container image used are
preserved in each downloaded run. [ADAPT.md](ADAPT.md) explains how to assemble
these sources and when to use the single-repository fallback. Repository separation uses the same synthetic calculations and does
not establish multiple human operators or operational fisheries use.

## Run locally and keep a copy

The [versioned release](https://github.com/kyuhank/fisheries-workflow-demo/releases/tag/v1.9.1)
provides an offline archive and a separate copy of the execution image. Keep
both to repeat the saved analyses if the website, GitHub account or image
registry becomes unavailable. The archive preserves the saved run's original
code and adds instructions for local use.

1. Unpack `fisheries-workflow-offline-1.9.1.zip` and open `START-HERE.html`.
   It links to saved reports, input records and the exact code, without a network
   connection. The interactive HTML also browses saved results offline.
2. Install and start Docker, then restore the supplied image as described in
   [OFFLINE.md](OFFLINE.md). Docker and a POSIX shell are the only host tools
   needed for this route; Windows users can use WSL. ARM computers require
   AMD64 emulation.
3. From the extracted folder, repeat and compare the saved analyses:

```sh
sh scripts/offline.sh reproduce
sh scripts/offline.sh compare
```

These commands run the R calculations and Quarto reports locally, with container
network access disabled. They use the preserved sources and image, without
GitHub Actions, a login, or host installations of Python, R, Quarto or Make.
New results go into `offline-runs/`; the saved reference remains available for
comparison. [OFFLINE.md](OFFLINE.md) also covers single jobs and updates.

**Download this run** saves the code, exact synthetic inputs, settings, records
and outputs. Save it before live results expire, about ten minutes after the last
run activity. Follow its `REPRODUCE.txt`; preserve the corresponding image as
well. A single-job download repeats that job and its required inputs; it does
not repeat every earlier result still in use.

## Work with the repository

For a Git checkout, the commands below assemble the pinned component sources
before starting the analyses. This development route needs Docker, Make,
Python 3 and Git and may retrieve source repositories and the image.
From the repository root:

```sh
make run                 # full workflow
make job JOB=cpue_a       # one job and its required inputs
```

Use [ADAPT.md](ADAPT.md) to change jobs and check their connections. See
[cloud/README.md](cloud/README.md) for hosting and [THIRD_PARTY.md](THIRD_PARTY.md)
for software sources and licences. Local calculations use the same analysis
code as hosted runs; the hosting service is a separate, optional facility.
