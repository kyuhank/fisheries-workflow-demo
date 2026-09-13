const payload = JSON.parse(document.getElementById("demo-payload").textContent);
const $ = (id) => document.getElementById(id);
const worker = new Worker(
  URL.createObjectURL(
    new Blob([$("worker-source").textContent], { type: "text/javascript" }),
  ),
);
const pending = new Map();
let sequence = 0,
  planVersion = 0,
  jobs = payload.jobs,
  records = {},
  states = {},
  plan = null;
let selected = "submission",
  busy = false,
  ready = false,
  currentOutput = null,
  latestRun = "",
  selectedTask = "";
let mode = "cloud";
const modeStates = {};
let offlineReady = false, cloudReady = false, offlineInit = null;
let completedSummary = null, modeVersion = 0;
let correctionPending = false;
let waitingTransfer = null;
const byKey = Object.fromEntries(jobs.map((job) => [job.key, job]));
const messages = [];

function localCall(type, data = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, type, payload: data });
  });
}

const cloud = new CloudRun(
  payload.cloud,
  jobs,
  handleEvent,
  (title, message, id) => {
    if (title) status("running", title, message);
    if (id) {
      $("github-run").href = "https://github.com/" + payload.cloud.repository +
        "/actions/runs/" + id;
      $("github-run").hidden = false;
    }
  },
);
function call(type, data = {}) {
  return mode === "cloud" ? cloud.call(type, data) : localCall(type, data);
}
async function initialiseOffline() {
  if (!offlineInit) {
    offlineInit = localCall("init", {
      runtime: payload.runtime,
      files: payload.files,
    })
      .then((result) => {
        offlineReady = true;
        return result;
      });
  }
  return offlineInit;
}

function settings() {
  return {
    last_year: Number($("snapshot").value),
    min_hooks_a: Number($("filter").value),
    mortality_2: Number($("mortality").value),
  };
}

function status(kind, title, message) {
  $("status").className = "status " + kind;
  $("status-title").textContent = title;
  $("status-message").textContent = message;
  $("status-icon").className = "status-icon" +
    (kind === "running" ? " spinner" : "");
  $("status-icon").textContent = kind === "running"
    ? ""
    : kind === "failed"
    ? "!"
    : kind === "complete"
    ? "✓"
    : "·";
}

function affectedByChange(key) {
  return plan?.changed.includes(key) ||
    byKey[key].parents.some(affectedByChange);
}

function stageStatus(key) {
  if (!busy && mode !== "saved" && records[key] && affectedByChange(key)) {
    return "outdated";
  }
  if (states[key]) return states[key];
  if (!records[key]) return "waiting";
  return records[key].run_id === latestRun ? "complete" : "retained";
}

const labels = {
  waiting: "Waiting",
  running: "Running",
  complete: "Complete",
  retained: "Retained",
  failed: "Failed",
  returned: "Correction",
  handover: "Awaiting file",
  received: "Received",
  outdated: "Needs update",
};
const symbols = {
  waiting: "○",
  complete: "✓",
  retained: "↶",
  failed: "!",
  returned: "↶",
  handover: "○",
  received: "✓",
  outdated: "↻",
};

function badge(key) {
  const state = stageStatus(key), span = document.createElement("span");
  span.className = "state";
  const symbol = document.createElement("span");
  symbol.className = "symbol" + (state === "running" ? " spinner" : "");
  symbol.textContent = symbols[state] || "";
  span.append(symbol, document.createTextNode(labels[state] || state));
  return span;
}

function selectJob(key) {
  selected = key;
  $("selection-title").textContent = byKey[key].title;
  $("selection-description").textContent = byKey[key].description;
  if (!busy && mode !== "saved") {
    completedSummary = null;
    refreshPlan();
  } else render();
}

function jobCard(key, layout) {
  const job = byKey[key],
    card = document.createElement("div"),
    state = stageStatus(key);
  card.className = "job " + state + (selected === key ? " selected" : "") +
    (plan?.run.includes(key) ? " in-path" : " outside-path") +
    (layout ? " diagram-job" : "") +
    (key === "database" ? " database-job" : "");
  card.dataset.job = key;
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute(
    "aria-label",
    job.title + ": " + (labels[state] || state) + ". Select starting job.",
  );
  card.onclick = () => selectJob(key);
  card.onkeydown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectJob(key);
    }
  };
  const title = document.createElement("h3");
  title.textContent = layout?.title || job.title;
  const origin = document.createElement("div");
  origin.className = "origin";
  origin.textContent = state === "retained" && records[key]
    ? records[key].run_id + " · saved"
    : records[key] && ["waiting", "handover", "outdated"].includes(state)
    ? "Previous: " + records[key].run_id
    : layout?.subtitle || "";
  const view = document.createElement("button");
  view.className = "view";
  view.textContent = "View ›";
  view.disabled = !records[key];
  view.setAttribute("aria-label", "View " + job.title + " output");
  view.onclick = (event) => {
    event.stopPropagation();
    openOutput(key);
  };
  view.onkeydown = (event) => event.stopPropagation();
  card.append(title, badge(key), origin, view);
  return card;
}

function svgElement(tag, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, value);
  }
  return element;
}

function roundedRoute(points) {
  let path = `M ${points[0].join(" ")}`;
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i - 1], b = points[i], c = points[i + 1];
    const before = Math.hypot(b[0] - a[0], b[1] - a[1]),
      after = Math.hypot(c[0] - b[0], c[1] - b[1]);
    const radius = Math.min(9, before / 2, after / 2);
    const entry = b.map((value, axis) =>
      value - (b[axis] - a[axis]) / before * radius
    );
    const leave = b.map((value, axis) =>
      value + (c[axis] - b[axis]) / after * radius
    );
    path += ` L ${entry.join(" ")} Q ${b.join(" ")} ${leave.join(" ")}`;
  }
  return path + ` L ${points.at(-1).join(" ")}`;
}

function renderDiagram() {
  const layout = payload.diagram;
  const svg = svgElement("svg", {
    viewBox: `0 0 ${layout.width} ${layout.height}`,
    class: "workflow-diagram",
    "aria-label": "Data management, CPUE analysis and stock assessment jobs",
  });
  const defs = svgElement("defs");
  for (
    const [name, colour] of Object.entries({
      muted: "#bac9d0",
      selected: "#1779a0",
      running: "#bb821f",
      saved: "#548c81",
      failed: "#b95139",
    })
  ) {
    const marker = svgElement("marker", {
      id: "arrow-" + name,
      markerWidth: 8,
      markerHeight: 8,
      refX: 7,
      refY: 4,
      orient: "auto",
      markerUnits: "userSpaceOnUse",
    });
    marker.append(
      svgElement("path", { d: "M 0 0 L 8 4 L 0 8 Z", fill: colour }),
    );
    defs.append(marker);
  }
  svg.append(defs);
  for (const group of layout.groups) {
    svg.append(
      svgElement("rect", {
        x: group.x,
        y: 42,
        width: group.width,
        height: 580,
        rx: 16,
        fill: group.fill,
        stroke: group.colour,
        "stroke-opacity": .22,
      }),
    );
    const title = svgElement("text", {
      x: group.x + 14,
      y: 24,
      fill: group.colour,
      class: "module-title",
    });
    title.textContent = group.title;
    svg.append(title);
  }
  for (const edge of layout.edges) {
    const inPath = plan?.run.includes(edge.from) && plan?.run.includes(edge.to);
    const receiving = busy && stageStatus(edge.to) === "running";
    const retained = plan?.retained.includes(edge.from) &&
      plan?.run.includes(edge.to);
    const awaiting = waitingTransfer &&
      ((waitingTransfer.boundary === "data" && edge.from === "extract" &&
        edge.to.startsWith("cpue_")) ||
        (waitingTransfer.boundary === "cpue" && edge.from.startsWith("cpue_") &&
          edge.to.startsWith("prepare_")));
    const kind = awaiting
      ? "failed"
      : receiving
      ? (retained ? "saved" : "running")
      : !busy && inPath && mode !== "saved"
      ? "selected"
      : "muted";
    svg.append(
      svgElement("path", {
        d: roundedRoute(edge.points),
        class: `connection ${kind} ${edge.kind}`,
        "data-from": edge.from,
        "data-to": edge.to,
        "marker-end": `url(#arrow-${kind})`,
      }),
    );
  }
  const loop = svgElement("path", {
    d: roundedRoute(layout.return.points),
    class: "connection return-path " +
      (correctionPending ? "failed active" : "muted"),
    "marker-end": "url(#arrow-" + (correctionPending ? "failed" : "muted") +
      ")",
  });
  svg.append(loop);
  if (correctionPending) {
    const text = svgElement("text", { x: 218, y: 287, class: "return-label" });
    for (const [i, line] of ["Correct +", "resubmit"].entries()) {
      const part = svgElement("tspan", { x: 218, dy: i ? 18 : 0 });
      part.textContent = line;
      text.append(part);
    }
    svg.append(text);
  }
  for (const label of layout.labels) {
    const text = svgElement("text", {
      x: label.x,
      y: label.y,
      class: "edge-label",
    });
    text.textContent = label.text;
    svg.append(text);
  }
  for (const node of layout.nodes) {
    const group = layout.groups.find((group) =>
      group.key === byKey[node.key].module
    );
    const foreign = svgElement("foreignObject", {
      x: node.x,
      y: node.y,
      width: node.width,
      height: node.height,
      overflow: "visible",
    });
    const card = jobCard(node.key, node);
    card.style.setProperty("--accent", group.colour);
    if (node.key === "database") {
      const state = stageStatus(node.key),
        inPath = plan?.run.includes(node.key);
      const cylinder = svgElement("g", {
        class: "database-shape " + state +
          (inPath ? " in-path" : " outside-path") +
          (selected === node.key ? " selected" : ""),
      });
      const { x, y, width: w, height: h } = node;
      cylinder.append(
        svgElement("path", {
          d: `M ${x} ${y + 13} A ${w / 2} 13 0 0 1 ${x + w} ${y + 13} V ${
            y + h - 13
          } A ${w / 2} 13 0 0 1 ${x} ${y + h - 13} Z`,
        }),
      );
      cylinder.append(
        svgElement("ellipse", { cx: x + w / 2, cy: y + 13, rx: w / 2, ry: 13 }),
      );
      svg.append(cylinder);
    }
    foreign.append(card);
    svg.append(foreign);
  }
  if ($("handover").value === "manual" && mode !== "saved") {
    for (const [boundary, x] of [["data", 383], ["cpue", 846]]) {
      const active = waitingTransfer?.boundary === boundary;
      const group = svgElement("g", {
        class: "handover-marker" + (active ? " active" : ""),
        transform: `translate(${x} 175)`,
      });
      group.append(
        svgElement("circle", { r: 15 }),
        svgElement("circle", { cx: 0, cy: -4, r: 3.5 }),
        svgElement("path", { d: "M -7 7 Q -7 0 0 0 Q 7 0 7 7" }),
      );
      const title = svgElement("title");
      title.textContent = boundary === "data"
        ? "Pass selected records to the CPUE analyst"
        : "Pass CPUE outputs to the assessment analyst";
      group.append(title);
      svg.append(group);
    }
  }
  $("workflow-view").classList.toggle("is-running", busy);
  $("workflow-view").replaceChildren(svg);
}

function render() {
  renderDiagram();
  const groups = [
    ["data", "Data management"],
    ["cpue", "CPUE analysis"],
    ["assessment", "Stock assessment"],
  ];
  $("job-table-body").replaceChildren();
  $("tasks").replaceChildren();
  for (const [module, title] of groups) {
    const members = jobs.filter((job) => job.module === module),
      active = members.filter((job) => stageStatus(job.key) === "running");
    const awaiting = members.find((job) => stageStatus(job.key) === "handover");
    const button = document.createElement("button");
    button.className = "task " + module +
      (active.length ? " running" : awaiting ? " awaiting" : "") +
      (selectedTask === module ? " active" : "");
    const name = document.createElement("strong");
    name.textContent = title;
    const summary = document.createElement("span");
    summary.textContent = active.length
      ? "Running · " + active.map((job) => job.title).join(", ")
      : awaiting
      ? "Awaiting file · " + awaiting.title
      : members.filter((job) => records[job.key]).length + " / " +
        members.length + " outputs available";
    button.append(name, summary);
    button.onclick = () => {
      selectedTask = module;
      $("task-title").textContent = title;
      render();
    };
    $("tasks").append(button);
  }
  for (const job of jobs) {
    if (selectedTask && job.module !== selectedTask) continue;
    const row = document.createElement("tr");
    row.className = stageStatus(job.key);
    row.dataset.job = job.key;
    for (const value of [job.title, job.owner]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    const inputs = document.createElement("small");
    inputs.className = "job-inputs";
    inputs.textContent = job.parents.length
      ? "Uses: " + job.parents.map((key) => byKey[key].title).join(" · ")
      : "Starts with the supplied records";
    row.firstChild.append(inputs);
    const state = document.createElement("td");
    state.append(badge(job.key));
    row.append(state);
    const origin = document.createElement("td");
    origin.textContent = records[job.key]?.run_id || "—";
    row.append(origin);
    const output = document.createElement("td"),
      button = document.createElement("button");
    button.className = "quiet";
    button.textContent = "View output";
    button.disabled = !records[job.key];
    button.onclick = () => openOutput(job.key);
    output.append(button);
    row.append(output);
    $("job-table-body").append(row);
  }
  $("run").disabled = !ready || busy || !plan || mode === "saved";
  $("run").hidden = mode === "saved";
  $("run").textContent = busy
    ? "Running…"
    : selected === "submission"
    ? "Run full workflow →"
    : "Run from this job →";
  $("download").disabled = busy || !Object.keys(records).length;
  $("reset").disabled = busy || !ready || mode === "saved";
  $("mode").disabled = busy;
  $("handover").disabled = busy || mode === "saved";
  $("handover-note").hidden = mode === "saved" ||
    $("handover").value !== "manual";
  $("revise-cpue").hidden = busy || !records.cpue_a;
  $("handover-panel").hidden = !waitingTransfer;
  for (const id of ["snapshot", "filter", "mortality"]) {
    $(id).disabled = busy || mode === "saved";
  }
  if (mode === "saved") {
    $("completion").textContent = "16 saved outputs";
    $("reuse-message").textContent =
      "A preserved execution. Select online or offline calculation to produce new results.";
  } else if (plan) {
    $("completion").textContent = completedSummary ||
      `${plan.run.length} jobs to run · ${plan.retained.length} retained`;
    const parentNames = byKey[selected].parents.filter((key) =>
      plan.retained.includes(key)
    ).map((key) => `${byKey[key].title} (${records[key]?.run_id})`);
    $("reuse-message").textContent = parentNames.length
      ? "Uses saved inputs: " + parentNames.join(" · ")
      : plan.retained.length
      ? "Other results keep their original run and files."
      : "";
    if (plan.changed.length && selected !== "submission") {
      $("reuse-message").textContent +=
        " Missing or changed inputs are rebuilt first.";
    }
  }
}

async function refreshPlan() {
  if (!ready || busy || mode === "saved") return;
  const version = ++planVersion;
  $("run").disabled = true;
  try {
    const next = await call("plan", { start: selected, settings: settings() });
    if (version === planVersion) {
      plan = next;
      render();
    }
  } catch (error) {
    showError(error);
  }
}

function showError(error) {
  busy = false;
  status("failed", "The analysis stopped", String(error));
  render();
}

function log(event) {
  const name = byKey[event.job]?.title || "Workflow";
  messages.push(`${name} · ${event.message || event.state}`);
  $("execution-log").textContent = messages.join("\n");
  $("execution-log").scrollTop = $("execution-log").scrollHeight;
}

function handleEvent(event) {
  if (event.state === "plan") {
    correctionPending = false;
    waitingTransfer = null;
    plan = event;
    latestRun = event.run_id;
    $("run-id").textContent = latestRun;
    states = Object.fromEntries(
      jobs.map(
        (job) => [job.key, plan.run.includes(job.key) ? "waiting" : "retained"],
      ),
    );
  } else {
    if (event.state === "handover") {
      waitingTransfer = event;
      $("handover-title").textContent = event.boundary === "data"
        ? "Data manager → CPUE analyst"
        : "CPUE analyst → Assessment analyst";
    } else if (event.state === "received") waitingTransfer = null;
    if (event.job === "qc" && event.state === "failed") {
      correctionPending = true;
    }
    if (event.job === "qc" && event.state === "complete") {
      correctionPending = false;
    }
    states[event.job] = event.state;
    if (event.record) records[event.job] = event.record;
    log(event);
    status(
      event.state === "failed"
        ? "failed"
        : event.state === "handover"
        ? "handover"
        : "running",
      event.state === "handover"
        ? "Waiting for the next analyst"
        : byKey[event.job].title,
      event.message,
    );
  }
  render();
}
worker.onmessage = ({ data }) => {
  if (data.type === "event") {
    if (mode === "live") handleEvent(data.event);
    return;
  }
  const request = pending.get(data.id);
  if (!request) return;
  pending.delete(data.id);
  if (data.type === "error") request.reject(new Error(data.error));
  else request.resolve(data.value);
};
worker.onerror = (event) => {
  offlineReady = false;
  for (const task of pending.values()) task.reject(new Error(event.message));
  pending.clear();
  if (mode === "live") {
    ready = false;
    showError(event.message);
  }
};

$("run").onclick = async () => {
  if (!ready || busy) return;
  busy = true;
  completedSummary = null;
  states = Object.fromEntries(
    jobs.map(
      (job) => [job.key, plan?.run.includes(job.key) ? "waiting" : "retained"],
    ),
  );
  messages.length = 0;
  $("execution-log").textContent = "";
  status(
    "running",
    "Starting the selected work",
    "Checking saved inputs and the selected settings.",
  );
  render();
  try {
    const result = await call("run", {
      start: selected,
      settings: settings(),
      handover: $("handover").value,
    });
    records = result.records;
    busy = false;
    latestRun = result.run_id;
    status(
      "complete",
      "Results are ready",
      `${result.run.length} ${
        result.run.length === 1 ? "job" : "jobs"
      } completed · ${result.retained.length} retained unchanged. Open a job to inspect its output.`,
    );
    completedSummary =
      `${result.run.length} completed · ${result.retained.length} retained`;
    await refreshPlan();
  } catch (error) {
    showError(error);
    await refreshPlan();
  }
};
for (const id of ["snapshot", "filter", "mortality"]) {
  $(id).onchange = () => {
    completedSummary = null;
    refreshPlan();
  };
}
$("handover").onchange = () => {
  status(
    "",
    "Connection mode selected",
    $("handover").value === "manual"
      ? "Calculations pause where inputs must pass to the next analyst."
      : "Recorded inputs pass directly to the dependent jobs.",
  );
  render();
};
$("revise-cpue").onclick = () => {
  $("filter").value = $("filter").value === "0" ? "1200" : "0";
  status(
    "",
    "CPUE A needs an update",
    "The effort filter has changed. The existing assessment still contains the earlier result. Run the revision to follow the handover.",
  );
  selectJob("cpue_a");
};
async function transferFiles(connect = false) {
  $("transfer-files").disabled = true;
  $("connect-workflow").disabled = true;
  try {
    await call("transfer", { connect });
    if (connect) $("handover").value = "connected";
    waitingTransfer = null;
    render();
  } catch (error) {
    status(
      "failed",
      "Transfer not confirmed",
      error.message + " Try the transfer again.",
    );
  } finally {
    $("transfer-files").disabled = false;
    $("connect-workflow").disabled = false;
  }
}
$("transfer-files").onclick = () => transferFiles();
$("connect-workflow").onclick = () => transferFiles(true);
$("reset").onclick = async () => {
  try {
    const result = await call("reset");
    completedSummary = null;
    records = result.records;
    states = {};
    latestRun = "";
    selected = "submission";
    $("snapshot").value = "2023";
    $("filter").value = "0";
    $("mortality").value = "0.30";
    $("run-id").textContent = "";
    messages.length = 0;
    $("execution-log").textContent = "No execution yet.";
    status(
      "",
      "Ready to run",
      "Begin with data submission, or select an analysis job.",
    );
    selectJob("submission");
  } catch (error) {
    status("failed", "Reset unavailable", error.message);
  }
};
for (const button of document.querySelectorAll("[data-tab]")) {
  button.onclick = () => {
    for (const other of document.querySelectorAll("[data-tab]")) {
      const active = other === button;
      other.classList.toggle("active", active);
      other.setAttribute("aria-selected", active);
    }
    $("workflow-view").hidden = button.dataset.tab !== "workflow";
    $("jobs-view").hidden = button.dataset.tab !== "jobs";
  };
}
function showRecord(show) {
  $("record-panel").hidden = !show;
  $("record-toggle").textContent = show ? "Hide record" : "Show record";
  $("record-toggle").setAttribute("aria-expanded", show);
}
$("record-toggle").onclick = () => showRecord($("record-panel").hidden);
$("record-close").onclick = () => showRecord(false);
$("all-tasks").onclick = () => {
  selectedTask = "";
  $("task-title").textContent = "All jobs";
  render();
};

function download(name, bytes, type) {
  const url = URL.createObjectURL(new Blob([bytes], { type })),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
$("download").onclick = async () => {
  try {
    const bytes = Uint8Array.from(
      atob(mode === "saved" ? payload.saved.bundle : await call("download")),
      (char) => char.charCodeAt(0),
    );
    download("fisheries-workflow-run.zip", bytes, "application/zip");
  } catch (error) {
    status("failed", "Download unavailable", error.message);
  }
};
function displayOutput(title, output, kind = "Job output") {
  currentOutput = output;
  $("output-title").textContent = title;
  $("output-kind").textContent = kind;
  $("output-frame").srcdoc = output.html;
  $("output-frame").hidden = false;
  $("output-json").hidden = true;
  document.querySelectorAll("[data-output]").forEach((button) => {
    button.classList.toggle("active", button.dataset.output === "report");
    button.disabled = button.dataset.output !== "report" && !output.record;
  });
  $("output-dialog").showModal();
}
async function openOutput(key) {
  try {
    displayOutput(
      byKey[key].title,
      mode === "saved"
        ? payload.saved.outputs[key]
        : await call("view", { job: key }),
      mode === "saved" ? "Saved example output" : "Job output",
    );
  } catch (error) {
    status("failed", "This output is unavailable", error.message);
  }
}
$("example").onclick = () =>
  displayOutput(
    "Assessment report",
    { html: payload.example },
    "Preserved example",
  );
$("licences").onclick = () => {
  const pre = document.createElement("pre");
  pre.textContent = payload.notices;
  displayOutput("Sources and licences", {
    html:
      '<!doctype html><meta charset="utf-8"><style>body{padding:24px;font:14px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>' +
      pre.outerHTML,
  }, "Preserved software");
};
$("output-close").onclick = () => $("output-dialog").close();
$("output-dialog").onclick = (event) => {
  if (event.target === $("output-dialog")) {
    const box = event.target.getBoundingClientRect();
    if (
      event.clientX < box.left || event.clientX > box.right ||
      event.clientY < box.top || event.clientY > box.bottom
    ) event.target.close();
  }
};
for (const button of document.querySelectorAll("[data-output]")) {
  button.onclick = () => {
    document.querySelectorAll("[data-output]").forEach((other) =>
      other.classList.toggle("active", other === button)
    );
    const report = button.dataset.output === "report";
    $("output-frame").hidden = !report;
    $("output-json").hidden = report;
    if (!report) {
      $("output-json").textContent = button.dataset.output === "log"
        ? currentOutput.record.log.join("\n")
        : JSON.stringify(
          currentOutput[
            button.dataset.output === "data" ? "output" : "record"
          ],
          null,
          2,
        );
    }
  };
}
$("save-output").onclick = () =>
  download("analysis-output.html", currentOutput.html, "text/html");

async function activateMode(next) {
  const version = ++modeVersion;
  modeStates[mode] = {
    records,
    states,
    latestRun,
    selected,
    completedSummary,
    messages: [...messages],
    settings: settings(),
  };
  mode = next;
  ready = false;
  plan = null;
  waitingTransfer = null;
  correctionPending = false;
  $("github-run").hidden = true;
  const saved = modeStates[mode];
  records = saved?.records || {};
  states = saved?.states || {};
  latestRun = saved?.latestRun || "";
  selected = saved?.selected || "submission";
  completedSummary = saved?.completedSummary || null;
  messages.splice(0, messages.length, ...(saved?.messages || []));
  $("execution-log").textContent = messages.join("\n") || "No execution yet.";
  if (saved?.settings) {
    $("snapshot").value = saved.settings.last_year;
    $("filter").value = saved.settings.min_hooks_a;
    $("mortality").value = Number(saved.settings.mortality_2).toFixed(2);
  }
  if (mode === "saved") {
    records = payload.saved.records;
    states = Object.fromEntries(jobs.map((job) => [job.key, "complete"]));
    latestRun = "Saved example";
    messages.length = 0;
    payload.saved.events.forEach(log);
    status(
      "",
      "Explore a saved execution",
      "Inspect every job, input, log and report. No calculation or internet connection is needed.",
    );
  } else {
    status(
      "running",
      mode === "cloud"
        ? "Connecting to the demonstration"
        : "Preparing offline calculation",
      mode === "cloud"
        ? "No account or installation is required."
        : "Loading the Python code and data included in this HTML file.",
    );
    render();
    try {
      if (mode === "cloud" && !cloudReady) {
        await cloud.initialise();
        cloudReady = true;
      }
      if (mode === "live" && !offlineReady) {
        const result = await initialiseOffline();
        records = result.records;
      }
      if (version !== modeVersion) return;
      ready = mode === "cloud" ? cloudReady : offlineReady;
      status(
        "",
        "Ready to run",
        mode === "cloud"
          ? "A free GitHub runner will download the Docker image and calculate the results."
          : "The preserved Python code runs here. Internet access is not needed.",
      );
      await refreshPlan();
    } catch (error) {
      if (version !== modeVersion) return;
      ready = false;
      status(
        "failed",
        "Online connection unavailable",
        error.message + " You can select Offline calculation or Saved example.",
      );
    }
  }
  $("run-id").textContent = latestRun;
  $("execution-note").textContent = mode === "cloud"
    ? "Online results expire after 10 minutes. Download a run to keep its code, data and results."
    : mode === "live"
    ? "Actual Python calculations in this browser tab. This HTML file also works offline."
    : "Previously calculated outputs, preserved inside this HTML file.";
  $("selection-title").textContent = byKey[selected].title;
  $("selection-description").textContent = byKey[selected].description;
  render();
}
$("mode").onchange = () => activateMode($("mode").value);
render();
activateMode("cloud");
