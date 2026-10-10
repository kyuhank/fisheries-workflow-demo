/** A readable job record, with links to the exact inputs and a checked rerun. */
const reproductionChecks = new Map();
function checkKey(record) {
  return [mode, record.job, record.run_id, record.signature].join(":");
}

function recordContext(output = currentOutput) {
  const key = output.record.job;
  const chain = traceInputs(key, records);
  return {
    schema_version: 1,
    job: key,
    original_run: output.record.run_id,
    description: byKey[key].description,
    settings: recordedSettings(chain, settings()),
    jobs: chain,
    job_descriptions: Object.fromEntries(
      Object.keys(chain).map((job) => [job, byKey[job].description]),
    ),
    comparison: output.comparison || null,
    reproduction: [
      "Download this run to retain its code, data, software details and reference outputs.",
      "Follow REPRODUCE.txt in the downloaded run. For a single-job run, it reproduces and compares that job; other saved outputs are kept as earlier results.",
      "Inspect code and software versions before comparing results. A job ID or checksum alone does not contain the underlying files.",
    ],
  };
}

function renderRecord() {
  const record = currentOutput.record, key = record.job;
  const panel = $("output-record");
  panel.replaceChildren();
  const heading = uiElement("div", "record-heading");
  const title = uiElement("div");
  title.append(
    uiElement("p", "eyebrow", "Recorded execution"),
    uiElement("h3", "", `${jobLabel(key)} · ${record.run_id}`),
    uiElement("p", "", byKey[key].description),
  );
  heading.append(title);
  panel.append(heading);

  if (currentOutput.comparison) {
    const check = currentOutput.comparison;
    const banner = uiElement(
      "div",
      "record-comparison " + (check.output_agrees ? "agrees" : "differs"),
    );
    banner.append(
      uiElement("strong", "", check.title),
      uiElement("p", "", check.message),
    );
    panel.append(banner);
  }
  const cards = uiElement("div", "record-cards");
  const source = record.analysis_source || record.source || {};
  const software = record.software || {};
  const image = record.execution?.container || software.container;
  for (
    const [label, value, detail] of [
      [
        "Data",
        `Snapshot ${record.snapshot}`,
        "Synthetic catch and effort records",
      ],
      [
        "Code",
        source.commit?.slice(0, 12) || "Saved source files",
        source.repository?.replace("https://github.com/", "") ||
        "SHA-256 recorded for each file",
      ],
      [
        "Container",
        image ? image.split("@")[0].split("/").pop() : "Image not recorded",
        image
          ? image.split("@")[0]
          : "Use the original run record",
      ],
    ]
  ) {
    const card = uiElement("div", "record-card");
    card.append(
      uiElement("span", "eyebrow", label),
      uiElement("strong", "", value),
      uiElement("small", "", detail),
    );
    if (label === "Container" && /^ghcr\.io\/[\w.-]+\/[\w.-]+@sha256:[a-f0-9]{64}$/.test(image || "")) {
      const [owner, name] = image.split("@")[0].slice("ghcr.io/".length).split("/");
      const link = uiElement("a", "record-image-link", "Container image ↗");
      link.href = `https://github.com/orgs/${encodeURIComponent(owner)}/packages/container/package/${encodeURIComponent(name)}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      card.append(link);
      card.append(uiElement("code", "record-image-digest", image.split("@")[1]));
      card.append(uiElement("small", "", [
        software.r && `R ${software.r}`,
        software.RTMB && `RTMB ${software.RTMB}`,
        software.quarto && `Quarto ${software.quarto}`,
      ].filter(Boolean).join(" · ")));
    }
    cards.append(card);
  }
  panel.append(cards);
  const repository = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(source.repository || "")
    ? source.repository : "https://github.com/kyuhank/fisheries-workflow-demo";
  const recordedRevision = /^[a-f0-9]{40}$/.test(source.commit || "") &&
      (record.analysis_source?.sha256 || Object.hasOwn(record.code || {}, `jobs/${key}/run.R`)) ? source.commit : null;
  const jobSource = uiElement("a", "record-source",
    recordedRevision ? "Job code & guide ↗" : "Current job code & guide ↗");
  const jobRepository = recordedRevision ? repository : "https://github.com/kyuhank/fisheries-workflow-demo";
  jobSource.href = `${jobRepository}/tree/${recordedRevision || "main"}/jobs/${encodeURIComponent(key)}`;
  jobSource.target = "_blank";
  jobSource.rel = "noopener noreferrer";
  panel.append(jobSource);
  if (
    /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(source.repository || "") &&
    /^[a-f0-9]{40}$/.test(source.commit || "")
  ) {
    const link = uiElement("a", "record-source", "Open recorded code ↗");
    link.href = source.repository + "/tree/" + source.commit;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    panel.append(link);
  }
  const execution = record.execution || {};
  if (/^[\w.-]+\/[\w.-]+$/.test(execution.repository || "") &&
      /^\d+$/.test(String(execution.github_run || ""))) {
    const link = uiElement("a", "record-source", "Open actual run ↗");
    link.href = `https://github.com/${execution.repository}/actions/runs/${execution.github_run}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    panel.append(link);
  }

  panel.append(uiElement("h3", "", "Inputs used by this job"));
  const list = uiElement("div", "record-inputs");
  for (const [parent, input] of Object.entries(record.inputs || {})) {
    const available = records[parent]?.run_id === input.run_id &&
      records[parent]?.outputs["output.json"] === input.checksum;
    const button = uiElement("button", "record-input");
    button.append(
      uiElement("strong", "", byKey[parent]?.title || parent),
      uiElement("span", "", `${input.run_id} · ${input.checksum.slice(0, 12)}`),
      uiElement(
        "small",
        "",
        available
          ? "Trace input ›"
          : "Earlier version · use its downloaded run",
      ),
    );
    button.disabled = !available;
    button.onclick = async () => {
      await openOutput(parent);
      if (currentOutput.record?.job === parent) {
        document.querySelector('[data-output="record"]').click();
      }
    };
    list.append(button);
  }
  if (!list.children.length) {
    list.append(
      uiElement(
        "p",
        "",
        "Starts with the supplied data files; their checksums are recorded below.",
      ),
    );
  }
  panel.append(list);

  let context, unavailable;
  try {
    context = recordContext();
  } catch (error) {
    unavailable = error.message;
  }
  const actions = uiElement("div", "record-actions");
  const rerun = uiElement("button", "primary", "Reproduce & compare");
  rerun.id = "reproduce-job";
  rerun.disabled = busy || mode === "saved" || !ready || !context;
  rerun.onclick = () => reproduceOutput(currentOutput, context);
  const save = uiElement("button", "quiet", "Download record");
  save.id = "download-job-record";
  save.onclick = () =>
    download(
      `${key}-record.json`,
      JSON.stringify(context || { job: key, record, unavailable }, null, 2),
      "application/json",
    );
  const copy = uiElement("button", "quiet", "Copy context");
  copy.id = "copy-job-context";
  copy.disabled = !context;
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(context, null, 2));
      copy.textContent = "Context copied";
    } catch {
      copy.textContent = "Download record to copy";
    }
  };
  actions.append(rerun, save, copy);
  panel.append(
    actions,
    uiElement(
      "p",
      "record-note",
      unavailable ||
        (mode === "saved"
          ? "To repeat this analysis, download this run and follow REPRODUCE.txt, or choose Live run on the website."
          : "Repeats the workflow with recorded settings and compares this result with the original."),
    ),
  );
  const details = uiElement("details", "record-details");
  details.append(
    uiElement("summary", "", "Full hashes, software and execution record"),
    uiElement(
      "pre",
      "",
      JSON.stringify(context || { record, unavailable }, null, 2),
    ),
  );
  panel.append(details);
}

async function comparisonAssessmentOutputs(expectedRecords) {
  return Object.fromEntries(await Promise.all(comparisonAssessmentJobs.map(async (job) => {
    const output = await call("view", { job }), expected = expectedRecords[job];
    if (!expected || output.record?.run_id !== expected.run_id ||
        output.record.outputs?.["output.json"] !== expected.outputs["output.json"]) {
      throw Error("The recorded assessment input is no longer available: " + job);
    }
    return [job, output.output];
  })));
}

async function reproduceOutput(reference, context) {
  if (busy || !ready) return;
  const key = reference.record.job;
  const copiedAssessment = ["assessment_summary", "assessment_report"].includes(key);
  let referenceAssessments;
  if (copiedAssessment) {
    busy = true;
    render();
    try {
      referenceAssessments = await comparisonAssessmentOutputs(context.jobs);
    } catch (error) {
      status("failed", "The original assessment inputs could not be read", error.message);
      return;
    } finally {
      busy = false;
      render();
    }
  }
  $("output-dialog").close();
  $("snapshot").value = context.settings.last_year;
  $("filter").value = context.settings.min_hooks_a;
  $("growth-rate").value = Number(context.settings.growth_rate_2).toFixed(2);
  $("mse-buffer").value = context.settings.mse_buffer ?? 0.8;
  $("handover").value = "connected";
  selected = "submission";
  executionScope = "workflow";
  settingsIntent = false;
  if (!await refreshPlan()) return;
  const result = await $("run").onclick();
  if (!result) return;
  busy = true;
  render();
  try {
    const output = await call("view", { job: key });
    let assessmentContext = null, mismatch = null;
    if (copiedAssessment) {
      const actualAssessments = await comparisonAssessmentOutputs(records);
      assessmentContext = Object.fromEntries(comparisonAssessmentJobs.map((job) =>
        [job, [referenceAssessments[job], actualAssessments[job]]]));
      for (const job of comparisonAssessmentJobs) {
        mismatch ||= compareOutput(...assessmentContext[job], job);
      }
    }
    mismatch ||= compareOutput(reference.output, output.output, key, assessmentContext);
    const changed = compareMaterials(context.jobs, records);
    const agrees = !mismatch;
    output.comparison = {
      reference_run: reference.record.run_id,
      reference_checksum: reference.record.outputs["output.json"],
      new_run: output.record.run_id,
      output_agrees: agrees,
      changed_materials: changed,
      reference_jobs: context.jobs,
      reference_output: reference.output,
      relative_tolerance: 1e-6,
      absolute_tolerance: 1e-9,
      assessment_gradient_magnitude_and_difference_limit: 1e-7,
      assessment_log_residual_absolute_tolerance: 1e-8,
      assessment_log_residual_invariant_tolerance: 1e-12,
      title: agrees
        ? (changed.length
          ? "Output agrees · execution materials changed"
          : "Reproduced · output agrees")
        : "Output differs from the reference",
      message: `${reference.record.run_id} → ${output.record.run_id}. ` +
        (mismatch
          ? `First difference: ${mismatch}. `
          : "Numerical comparison passed using the recorded comparison criteria. ") +
        (changed.length
          ? "Changed: " + changed.join(", ") + "."
          : "Recorded code, data files, settings and software matched."),
    };
    for (const stored of reproductionChecks.keys()) {
      if (stored.startsWith(`${mode}:${key}:`)) {
        reproductionChecks.delete(stored);
      }
    }
    reproductionChecks.set(checkKey(output.record), output.comparison);
    busy = false;
    displayOutput(byKey[key].title, output, "Reproduction check");
    document.querySelector('[data-output="record"]').click();
  } catch (error) {
    status("failed", "The comparison could not be completed", error.message);
  } finally {
    busy = false;
    render();
  }
}
