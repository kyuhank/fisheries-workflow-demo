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
      "python3 run.py --settings settings.json --output reproduced",
      "python3 verify.py reference reproduced",
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
    uiElement("h3", "", `${key} · ${record.run_id}`),
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
  const source = record.source || {};
  const software = record.software || {};
  const image = record.execution?.container;
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
        "Software",
        image ? "Docker image" : software.runtime,
        image
          ? image.split("@")[0]
          : `Python ${software.python} · SQLite ${software.sqlite}`,
      ],
    ]
  ) {
    const card = uiElement("div", "record-card");
    card.append(
      uiElement("span", "eyebrow", label),
      uiElement("strong", "", value),
      uiElement("small", "", detail),
    );
    cards.append(card);
  }
  panel.append(cards);
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
          ? "This is a saved example. Select a calculation mode to run new results."
          : "Recalculates the workflow from the recorded inputs and settings, then compares this job’s output. Other jobs will also run."),
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

async function reproduceOutput(reference, context) {
  if (busy || !ready) return;
  const key = reference.record.job;
  $("output-dialog").close();
  $("snapshot").value = context.settings.last_year;
  $("filter").value = context.settings.min_hooks_a;
  $("mortality").value = Number(context.settings.mortality_2).toFixed(2);
  $("handover").value = "connected";
  selected = "submission";
  await refreshPlan();
  const result = await $("run").onclick();
  if (!result) return;
  try {
    const output = await call("view", { job: key });
    const mismatch = compareOutput(reference.output, output.output);
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
      title: agrees
        ? (changed.length
          ? "Output agrees · execution materials changed"
          : "Reproduced · output agrees")
        : "Output differs from the reference",
      message: `${reference.record.run_id} → ${output.record.run_id}. ` +
        (mismatch
          ? `First difference: ${mismatch}. `
          : "Numerical comparison passed (relative 1e−6; absolute 1e−9). ") +
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
    displayOutput(byKey[key].title, output, "Reproduction check");
    document.querySelector('[data-output="record"]').click();
  } catch (error) {
    status("failed", "The comparison could not be completed", error.message);
  }
}
