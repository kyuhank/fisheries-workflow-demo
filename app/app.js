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
  selectedTask = "data";
let mode = "cloud";
const modeStates = {};
let offlineReady = false, cloudReady = false, offlineInit = null;
let completedSummary = null, modeVersion = 0;
let correctionPending = false;
let activities = {}, dispatchPending = false;
let workspaceView = "tasks", jobStatusFilter = "";
let waitingTransfer = null;
let confirmingTransfer = false;
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
    offlineInit = loadOfflineRuntime()
      .then(() => {
        offlineLoading("Starting Python with the supplied code and data.");
        return localCall("init", { runtime: payload.runtime, files: payload.files });
      })
      .then((result) => {
        offlineReady = true;
        return result;
      })
      .catch((error) => {
        offlineInit = null;
        throw error;
      });
  }
  return offlineInit;
}

function offlineLoading(message) {
  if (mode === "live" && !ready) status("running", "Preparing Offline run", message);
}

async function loadOfflineRuntime() {
  if (payload.runtime) return;
  const controller = new AbortController();
  let timeout;
  const watch = () => {
    clearTimeout(timeout);
    timeout = setTimeout(() => controller.abort(), 20000);
  };
  watch();
  try {
    offlineLoading("Downloading Python once for this tab. Save the offline demo for use without internet.");
    const response = await fetch(new URL(payload.runtimeUrl, location.href), {
      signal: controller.signal,
    });
    if (!response.ok) throw Error("The offline runtime could not be downloaded. Try again when connected.");
    const reader = response.body.getReader(), decoder = new TextDecoder();
    const parts = [];
    let received = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      parts.push(decoder.decode(value, { stream: true }));
      watch();
      offlineLoading(`Downloading Python · ${(received / 1e6).toFixed(1)} / ${(payload.runtimeBytes / 1e6).toFixed(1)} MB`);
    }
    parts.push(decoder.decode());
    payload.runtime = JSON.parse(parts.join(""));
  } catch (error) {
    if (controller.signal.aborted) {
      throw Error("The offline download stopped responding. Retry when connected, or open the downloaded offline demo.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function settings() {
  return {
    last_year: Number($("snapshot").value),
    min_hooks_a: Number($("filter").value),
    mortality_2: Number($("mortality").value),
  };
}

function status(kind, title, message) {
  $("offline-fallback").hidden = true;
  $("retry-connection").hidden = true;
  $("status").className = "status " + kind;
  $("status-title").textContent = title;
  $("status-message").textContent = message;
  $("status-icon").className = "status-icon" +
    (kind === "running" ? " spinner" : "");
  $("status-icon").replaceChildren();
  if (kind !== "running") {
    $("status-icon").append(
      lineIcon(
        kind === "failed" ? "alert" : kind === "complete" ? "check" : "clock",
      ),
    );
  }
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
  outdated: "Inputs changed",
};
const symbols = {
  waiting: "clock",
  complete: "check",
  retained: "restore",
  failed: "alert",
  returned: "restore",
  handover: "clock",
  received: "check",
  outdated: "restore",
};

function statusSymbol(state) {
  const symbol = uiElement(
    "span",
    "symbol" + (state === "running" ? " spinner" : ""),
  );
  symbol.setAttribute("aria-hidden", "true");
  if (state !== "running") symbol.append(lineIcon(symbols[state] || "clock"));
  return symbol;
}

function statusLabel(key) {
  return activities[key] === "resubmit" && stageStatus(key) === "running"
    ? "Resubmit"
    : labels[stageStatus(key)];
}

function badge(key) {
  const state = stageStatus(key), span = document.createElement("span");
  span.className = "state";
  span.append(
    statusSymbol(state),
    document.createTextNode(statusLabel(key) || state),
  );
  return span;
}

function selectJob(key) {
  selected = key;
  selectedTask = byKey[key].module;
  $("selection-title").textContent = byKey[key].title;
  $("selection-description").textContent = byKey[key].description;
  if (!busy && mode !== "saved") {
    completedSummary = null;
    refreshPlan();
  } else render();
}

function jobNode(node, colour) {
  const key = node.key, job = byKey[key], state = stageStatus(key);
  const inPath = mode === "saved" || plan?.run.includes(key), database = key === "database";
  const card = svgElement("g", {
    class: "job workflow-node " + state +
      (selected === key ? " selected" : "") +
      (dispatchPending && key === plan?.run[0] ? " queued-start" : "") +
      (inPath ? " in-path" : " outside-path"),
    transform: `translate(${node.x} ${node.y})`,
    "data-job": key,
    "data-activity": activities[key] || "",
    role: "button",
    tabindex: 0,
    "aria-label": job.title + ": " + (statusLabel(key) || state) +
      ". Select starting job.",
  });
  card.style.setProperty("--accent", colour);
  card.onclick = () => selectJob(key);
  card.onkeydown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectJob(key);
    }
  };
  const w = node.width, h = node.height;
  const shape = database
    ? svgElement("path", {
      d: `M 0 13 A ${w / 2} 13 0 0 1 ${w} 13 V ${h - 13} A ${
        w / 2
      } 13 0 0 1 0 ${h - 13} Z`,
    })
    : svgElement("rect", { width: w, height: h, rx: 11 });
  const outline = shape.cloneNode();
  outline.setAttribute("class", "node-outline");
  shape.setAttribute("class", "node-shape");
  card.append(outline, shape);
  if (database) {
    card.append(
      svgElement("ellipse", {
        cx: w / 2,
        cy: 13,
        rx: w / 2,
        ry: 13,
        class: "node-cap",
      }),
    );
  }

  const titles = {
    submission: ["Data", "submission"],
    cpue_a: ["CPUE analysis", "A"],
    cpue_b: ["CPUE analysis", "B"],
    assessment_summary: ["Results", "summary"],
    assessment_report: ["Assessment", "report"],
  };
  const lines = titles[key] || [node.title];
  const titleY = database ? 44 : 26;
  const title = svgElement("text", { x: 14, y: titleY, class: "node-title" });
  for (const [index, line] of lines.entries()) {
    const part = svgElement("tspan", { x: 14, y: titleY + index * 20 });
    part.textContent = line;
    title.append(part);
  }
  card.append(title);
  const statusY = titleY + (lines.length - 1) * 20 + 24;
  const status = svgElement("g", {
    class: "node-status",
    transform: `translate(14 ${statusY - 12})`,
  });
  if (state === "running") {
    const spinner = svgElement("circle", {
      cx: 7,
      cy: 7,
      r: 5.5,
      class: "node-spinner",
    });
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      spinner.append(
        svgElement("animateTransform", {
          attributeName: "transform",
          type: "rotate",
          from: "0 7 7",
          to: "360 7 7",
          dur: "1s",
          repeatCount: "indefinite",
        }),
      );
    }
    status.append(spinner);
  } else {
    const icon = lineIcon(symbols[state] || "clock");
    icon.setAttribute("class", "node-status-icon");
    icon.setAttribute("width", "14");
    icon.setAttribute("height", "14");
    status.append(icon);
  }
  const statusText = svgElement("text", { x: 22, y: 12 });
  statusText.textContent = statusLabel(key) || state;
  status.append(statusText);
  card.append(status);

  const summary = key === "cpue_summary" || key === "assessment_summary";
  if (summary) {
    const subtitle = svgElement("text", {
      x: 14,
      y: statusY + 22,
      class: "node-origin",
    });
    subtitle.textContent = node.subtitle;
    card.append(subtitle);
  }

  const prior = records[key] &&
    ["retained", "waiting", "handover", "outdated"].includes(state);
  const origin = svgElement("text", {
    x: database ? w / 2 : 14,
    y: database ? 17 : h - 11,
    "text-anchor": database ? "middle" : "start",
    class: "node-origin",
  });
  origin.textContent = prior
    ? records[key].run_id
    : summary
    ? ""
    : node.subtitle || "";
  card.append(origin);

  const view = svgElement("g", {
    class: "view node-view",
    transform: `translate(${w - 51} ${h - 26})`,
    role: "button",
    tabindex: records[key] ? 0 : -1,
    "aria-disabled": String(!records[key]),
    "aria-label": "View " + job.title + " output",
  });
  view.append(svgElement("rect", { width: 44, height: 22, rx: 4 }));
  const viewText = svgElement("text", {
    x: 22,
    y: 15,
    "text-anchor": "middle",
  });
  viewText.textContent = "View ›";
  view.append(viewText);
  const open = (event) => {
    event.stopPropagation();
    if (records[key]) openOutput(key);
  };
  view.onclick = open;
  view.onkeydown = (event) => {
    event.stopPropagation();
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open(event);
    }
  };
  card.append(view);
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
      handover: "#b27b2d",
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
    const awaiting = waitingTransfer?.group.includes(edge.to) &&
      ((waitingTransfer.boundary === "data" && edge.from === "extract" &&
        edge.to.startsWith("cpue_")) ||
        (waitingTransfer.boundary === "cpue" && edge.from.startsWith("cpue_") &&
          edge.to.startsWith("prepare_")));
    const kind = awaiting
      ? "handover"
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
    for (const [i, line] of ["Correct +", "Resubmit"].entries()) {
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
    svg.append(jobNode(node, group.colour));
  }
  if ($("handover").value === "manual" && mode !== "saved") {
    for (const [boundary, x, y, to] of [
      ["data", 383, 175, "cpue_a"], ["data", 383, 487, "cpue_b"],
      ["cpue", 846, 175, "prepare_a"], ["cpue", 846, 487, "prepare_b"],
    ]) {
      const active = waitingTransfer?.boundary === boundary &&
        waitingTransfer.group.includes(to);
      const group = svgElement("g", {
        class: "handover-marker" + (active ? " active" : ""),
        transform: `translate(${x} ${y})`,
        "data-boundary": boundary,
        "data-to": to,
      });
      group.append(
        svgElement("circle", { r: 15 }),
        svgElement("circle", { cx: 0, cy: -4, r: 3.5 }),
        svgElement("path", { d: "M -7 7 Q -7 0 0 0 Q 7 0 7 7" }),
      );
      const title = svgElement("title");
      title.textContent = (active ? "Confirm file transfer to " : "Manual file transfer to ") +
        byKey[to].title;
      group.append(title);
      svg.append(group);
    }
  }
  $("workflow-view").classList.toggle("is-running", busy);
  $("workflow-view").replaceChildren(svg);
}

const taskGroups = [
  {
    key: "data",
    title: "Data management",
    description: "Submit, check and extract records.",
    icon: "database",
  },
  {
    key: "cpue",
    title: "CPUE analysis",
    description: "Standardise, compare and report indices.",
    icon: "chart",
  },
  {
    key: "assessment",
    title: "Stock assessment",
    description: "Prepare inputs, fit models and report results.",
    icon: "layers",
  },
];

function uiElement(tag, className = "", text) {
  const element = document.createElement(tag);
  element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function lineIcon(name) {
  const icon = svgElement("svg", {
    viewBox: "0 0 24 24",
    "aria-hidden": "true",
    class: "line-icon",
  });
  const paths = {
    folder: "M3 6h7l2 3h9v11H3Z M3 6V4h7l2 2h9v3",
    list: "M8 6h13M8 12h13M8 18h13M3 6h1M3 12h1M3 18h1",
    database:
      "M4 6c0-4 16-4 16 0s-16 4-16 0m0 0v12c0 4 16 4 16 0V6M4 12c0 4 16 4 16 0",
    chart: "M4 4v16h16M7 15l4-5 4 2 5-7",
    layers: "M3 7l9-4 9 4-9 4-9-4m0 5 9 4 9-4M3 17l9 4 9-4",
    file: "M6 3h8l4 4v14H6V3m8 0v5h4M9 12h6m-6 4h6",
    person: "M8 7a4 4 0 1 0 8 0 4 4 0 1 0-8 0M4 21v-2a8 8 0 0 1 16 0v2",
    check: "M5 12l4 4L19 6",
    clock: "M12 3a9 9 0 1 0 0 18 9 9 0 1 0 0-18M12 7v5l3 2",
    restore: "M4 11a8 8 0 1 1 1 6M4 5v6h6",
    alert: "M12 3l10 18H2L12 3zM12 9v5m0 3v.1",
  };
  icon.append(svgElement("path", { d: paths[name] }));
  return icon;
}

function renderTasks() {
  $("tasks").replaceChildren();
  for (const task of taskGroups) {
    const members = jobs.filter((job) => job.module === task.key);
    const active = members.filter((job) => stageStatus(job.key) === "running");
    const awaiting = members.find((job) => stageStatus(job.key) === "handover");
    const failed = members.find((job) => stageStatus(job.key) === "failed");
    const outdated = members.find((job) => stageStatus(job.key) === "outdated");
    const available = members.filter((job) => records[job.key]).length;
    const completed = members.filter((job) => stageStatus(job.key) === "complete").length;
    const reused = members.filter((job) => stageStatus(job.key) === "retained").length;
    const resolved = members.every((job) =>
      ["complete", "retained"].includes(stageStatus(job.key))
    );
    const state = active.length
      ? "running"
      : failed
      ? "failed"
      : awaiting
      ? "handover"
      : outdated
      ? "outdated"
      : resolved
      ? (reused === members.length ? "retained" : "complete")
      : "waiting";
    const button = uiElement(
      "button",
      "task " + task.key + " " + state +
        (selectedTask === task.key ? " active" : ""),
    );
    button.setAttribute("aria-pressed", String(selectedTask === task.key));
    const heading = uiElement("span", "task-card-heading");
    const icon = uiElement("span", "task-icon");
    icon.append(lineIcon(task.icon));
    const name = uiElement("strong", "task-name", task.title);
    const status = uiElement("span", "task-status " + state);
    status.append(statusSymbol(state), document.createTextNode(state === "retained" ? "Reused" : labels[state]));
    heading.append(icon, name, status);
    const description = uiElement("span", "task-description", task.description);
    const responsibility = uiElement("span", "task-responsibility");
    responsibility.append(lineIcon("person"), uiElement("span", "",
      [...new Set(members.map((job) => job.owner))].join(" · ")));
    const progress = uiElement("span", "task-progress");
    progress.setAttribute("aria-hidden", "true");
    for (const job of members) {
      const segment = uiElement("span", stageStatus(job.key));
      segment.title = job.title + ": " + labels[stageStatus(job.key)];
      progress.append(segment);
    }
    const footer = uiElement("span", "task-footer");
    footer.append(
      uiElement("span", "", completed || reused
        ? [completed && `${completed} complete`, reused && `${reused} reused`].filter(Boolean).join(" · ")
        : `${available}/${members.length} outputs available`),
      uiElement("span", "task-open", `${members.length} jobs ›`),
    );
    const activity = uiElement(
      "span",
      "task-activity",
      (active.length > 1
        ? `${active.length} jobs running together`
        : active.length
        ? (activities[active[0].key] === "resubmit"
          ? "Resubmit corrected data"
          : active[0].title)
        : "") ||
        (awaiting ? "Waiting for file transfer" : "") || failed?.title ||
        (outdated ? "Updated inputs need a rerun" : ""),
    );
    activity.hidden = !activity.textContent;
    button.append(heading, description, responsibility, progress, activity, footer);
    button.onclick = () => {
      selectedTask = task.key;
      workspaceView = "jobs";
      jobStatusFilter = "";
      render();
    };
    $("tasks").append(button);
  }
  $("task-title").textContent =
    taskGroups.find((task) => task.key === selectedTask)?.title || "All jobs";
  const activeJobs = jobs.filter((job) => stageStatus(job.key) === "running");
  $("running-count").textContent = activeJobs.length;
  $("workspace-activity").replaceChildren(
    statusSymbol(
      activeJobs.length
        ? "running"
        : waitingTransfer
        ? "handover"
        : busy || !Object.keys(records).length
        ? "waiting"
        : "complete",
    ),
    document.createTextNode(
      activeJobs.length
        ? `${activeJobs.length} running`
        : waitingTransfer
        ? "Awaiting file transfer"
        : busy
        ? "Waiting"
        : Object.keys(records).length
        ? "Results available"
        : "Ready",
    ),
  );
  $("workspace-activity").classList.toggle("running", activeJobs.length > 0);
  $("workspace-activity").classList.toggle("handover", Boolean(waitingTransfer));
  $("tasks").hidden = workspaceView !== "tasks";
  $("task-jobs").hidden = workspaceView !== "jobs";
  $("workspace-breadcrumb").textContent = workspaceView === "tasks"
    ? "Task overview"
    : "Task overview / Jobs";
  $("workspace-title").textContent = workspaceView === "tasks"
    ? "Follow the work across teams"
    : $("task-title").textContent;
  $("workspace-description").textContent = workspaceView === "tasks"
    ? "See who owns each job, what it needs, and the record behind its result."
    : "Follow required inputs; open the output or its recorded inputs and versions.";
  $("task-filter").value = selectedTask || "";
  $("job-status-filter").value = jobStatusFilter;
  $("show-tasks").classList.toggle("active", workspaceView === "tasks");
  $("all-tasks").classList.toggle(
    "active",
    workspaceView === "jobs" && !jobStatusFilter,
  );
  $("running-jobs").classList.toggle(
    "active",
    workspaceView === "jobs" && jobStatusFilter === "running",
  );
}

function jobProgress(job) {
  const state = stageStatus(job.key);
  const pendingInputs = job.parents.filter((key) =>
    !["complete", "retained"].includes(stageStatus(key)));
  const detail = state === "handover" ? "Confirm file transfer to continue"
    : state === "retained" ? "Earlier result kept unchanged"
    : state === "outdated" ? "Rerun with the updated inputs"
    : state === "failed" ? "Open the execution log"
    : state === "waiting" && pendingInputs.length
    ? "After " + byKey[pendingInputs[0]].title + (pendingInputs.length > 1 ? ` + ${pendingInputs.length - 1} more` : "")
    : state === "waiting" ? (busy ? "Inputs available · queued" : "Inputs available")
    : "";
  const label = state === "retained" ? "Reused"
    : state === "waiting" && !pendingInputs.length && !busy ? "Ready"
    : statusLabel(job.key);
  return { state, detail, label };
}

async function openJobRecord(key) {
  await openOutput(key);
  if (currentOutput?.record?.job === key && $("output-dialog").open) {
    document.querySelector('[data-output="record"]').click();
  }
}

function renderJobTable() {
  $("job-table-body").replaceChildren();
  for (const job of jobs) {
    if (selectedTask && job.module !== selectedTask) continue;
    if (jobStatusFilter && stageStatus(job.key) !== jobStatusFilter) continue;
    const row = document.createElement("tr");
    const progress = jobProgress(job);
    row.className = stageStatus(job.key) +
      (selected === job.key ? " selected-job" : "");
    row.dataset.job = job.key;
    row.dataset.module = job.module;
    const name = document.createElement("td");
    name.className = "job-name-cell";
    const select = uiElement("button", "job-name", job.title);
    select.onclick = () => selectJob(job.key);
    select.setAttribute("aria-label", "Run from " + job.title);
    name.append(select);
    const owner = uiElement("td", "job-owner");
    owner.dataset.label = "Responsible";
    const ownerLabel = uiElement("span", "owner-label");
    ownerLabel.append(lineIcon("person"), document.createTextNode(job.owner));
    owner.append(ownerLabel);
    row.append(name, owner);
    const inputs = uiElement("div", "job-inputs");
    inputs.append(uiElement("span", "input-caption", job.parents.length ? "Inputs" : "Supplied catch and effort records"));
    for (const key of job.parents) {
      const input = records[job.key]?.inputs?.[key];
      const earlierVersion = input && (input.run_id !== records[key]?.run_id ||
        input.checksum !== records[key]?.outputs?.["output.json"]);
      const link = uiElement("button", "input-link", byKey[key].title);
      link.dataset.inputJob = key;
      link.disabled = Boolean(earlierVersion);
      link.title = earlierVersion ? "Earlier input version · open this job’s Record"
        : records[key] ? `Inspect input record · ${records[key].run_id}` : "Select this input job";
      link.onclick = () => records[key] ? openJobRecord(key) : selectJob(key);
      inputs.append(link);
    }
    row.firstChild.append(inputs);
    const state = document.createElement("td");
    const progressBadge = badge(job.key);
    progressBadge.lastChild.textContent = progress.label;
    if (progress.label === "Ready") progressBadge.classList.add("ready");
    state.className = "job-progress";
    state.append(progressBadge);
    if (progress.detail) state.append(uiElement("small", "progress-detail", progress.detail));
    row.append(state);
    const origin = document.createElement("td");
    origin.className = "job-origin";
    origin.dataset.label = "Output from";
    origin.append(
      uiElement("span", "run-label", records[job.key]?.run_id || "—"),
    );
    row.append(origin);
    const output = document.createElement("td"),
      button = document.createElement("button");
    button.className = "open-output";
    button.append(lineIcon("file"), document.createTextNode("Output"));
    button.setAttribute("aria-label", "Open " + job.title + " output");
    button.disabled = !records[job.key];
    button.onclick = () => openOutput(job.key);
    const recordButton = uiElement("button", "open-job-record", "Record");
    recordButton.disabled = !records[job.key];
    recordButton.setAttribute("aria-label", "Inspect " + job.title + " recorded inputs and versions");
    recordButton.onclick = () => openJobRecord(job.key);
    output.className = "job-inspect";
    output.append(button, recordButton);
    row.append(output);
    $("job-table-body").append(row);
  }
  const count = $("job-table-body").children.length;
  $("task-subtitle").textContent = `${count} ${count === 1 ? "job" : "jobs"}`;
  if (!count) {
    const row = document.createElement("tr"),
      cell = uiElement("td", "empty-jobs", "No jobs in this state.");
    cell.colSpan = 5;
    row.append(cell);
    $("job-table-body").append(row);
  }
}

function render() {
  renderDiagram();
  renderTasks();
  renderJobTable();
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
  $("handover-note").hidden = Boolean(waitingTransfer) || mode === "saved" ||
    $("handover").value !== "manual";
  $("handover-help").textContent = $("handover").value === "manual"
    ? "Confirm each file transfer to continue."
    : "Pass inputs automatically.";
  $("revise-cpue").hidden = busy || !records.cpue_a;
  $("handover-panel").hidden = !waitingTransfer;
  $("transfer-files").disabled = confirmingTransfer;
  $("connect-workflow").disabled = confirmingTransfer;
  $("transfer-files").textContent = confirmingTransfer
    ? "Confirming transfer…"
    : "Confirm file transfer →";
  const manual = $("handover").value === "manual" && mode !== "saved";
  document.querySelector('[data-tab="jobs"]').textContent = manual ? "Job outputs" : "Orchestration tool";
  document.querySelector('.workspace-brand .eyebrow').textContent = manual ? "Separate workspaces" : "Orchestration";
  document.querySelector('.workspace-brand strong').textContent = manual ? "Job outputs" : "Analysis workspace";
  document.querySelector('.workspace-nav').setAttribute('aria-label', manual
    ? "Job outputs navigation" : "Orchestration navigation");
  if (manual) $("workspace-description").textContent =
    "Separate workspaces, without shared orchestration. Inspect each analyst’s jobs, inputs and results.";
  for (const id of ["snapshot", "filter", "mortality"]) {
    $(id).disabled = busy || mode === "saved";
  }
  $("selection-label").textContent = mode === "saved" ? "Selected job" : "Start from";
  $("hint").textContent = mode === "saved"
    ? "Use View to inspect a job’s outputs and inputs."
    : "Select a job to rerun it and the analyses that use its output.";
  if (mode === "saved") {
    $("completion").textContent = "16 saved outputs";
    $("reuse-message").textContent = "";
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
  const version = ++planVersion, executionMode = mode;
  $("run").disabled = true;
  try {
    const next = await call("plan", { start: selected, settings: settings() });
    if (version === planVersion && executionMode === mode) {
      plan = next;
      explainChanges();
      render();
    }
  } catch (error) {
    if (version === planVersion && executionMode === mode) showError(error);
  }
}

function explainChanges() {
  const changes = [];
  const previous = records.submission?.settings.last_year;
  if (previous && previous !== settings().last_year) {
    changes.push(`Data snapshot: ${previous} → ${settings().last_year}`);
  }
  const filter = records.cpue_a?.settings.min_hooks;
  if (filter !== undefined && filter !== settings().min_hooks_a) {
    changes.push("CPUE A record selection changed");
  }
  if (["assessment_a2", "assessment_b2"].some((key) =>
    records[key] && records[key].settings.M !== settings().mortality_2
  )) changes.push("Assessment mortality setting changed");
  if (changes.length) {
    status("settings-changed", "New settings · previous results kept",
      changes.join(" · ") + ". Run to update the affected jobs.");
  } else if ($("status").classList.contains("settings-changed")) {
    status("complete", "Previous settings restored", "Saved results match these settings.");
  }
}

function showError(error) {
  busy = false;
  dispatchPending = false;
  waitingTransfer = null;
  confirmingTransfer = false;
  status("failed", "The analysis stopped", String(error));
  $("offline-fallback").hidden = mode !== "cloud";
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
    activities = {};
    waitingTransfer = null;
    confirmingTransfer = false;
    plan = event;
    latestRun = event.run_id;
    $("run-id").textContent = latestRun;
    states = Object.fromEntries(
      jobs.map(
        (job) => [job.key, plan.run.includes(job.key) ? "waiting" : "retained"],
      ),
    );
  } else {
    dispatchPending = false;
    if (["running", "handover", "received"].includes(event.state) && event.group) {
      for (const key of event.group) {
        states[key] = event.state;
        activities[key] = "";
      }
    }
    activities[event.job] = event.activity || "";
    if (event.state === "handover") {
      waitingTransfer = { ...event, group: event.group || [event.job] };
      confirmingTransfer = false;
      $("handover-title").textContent = event.boundary === "data"
        ? "Data manager → CPUE analyst"
        : "CPUE analyst → Assessment analyst";
      $("handover-message").textContent = "Separate workspaces · no shared orchestration. Confirm that the updated files have been transferred.";
    } else if (event.state === "received") {
      waitingTransfer = null;
      confirmingTransfer = false;
    }
    if (event.job === "qc" && event.state === "failed") {
      correctionPending = true;
    }
    if (event.job === "submission" && event.state === "returned") {
      states.qc = "waiting";
    }
    if (event.job === "qc" && ["running", "complete"].includes(event.state)) {
      correctionPending = false;
    }
    states[event.job] = event.state;
    if (event.record) records[event.job] = event.record;
    log(event);
    const active = jobs.filter((job) => states[job.key] === "running");
    const groupTitle = active.length > 1
      ? `${active.length} jobs running together`
      : "";
    status(
      event.state === "failed"
        ? "failed"
        : waitingTransfer
        ? "handover"
        : "running",
      waitingTransfer
        ? "File transfer required · click to continue"
        : event.activity === "resubmit"
        ? "Resubmit corrected data"
        : event.state === "returned"
        ? "Correct the submission"
        : groupTitle || byKey[event.job].title,
      waitingTransfer
        ? waitingTransfer.group.map((key) => byKey[key].title).join(" and ") +
          (waitingTransfer.group.length > 1 ? " await" : " awaits") +
          " updated inputs. Confirm the transfer below to continue."
        : groupTitle
        ? active.map((job) => job.title).join(" · ") +
          ". Dependent stages wait for their input group to finish."
        : event.message,
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
  dispatchPending = true;
  correctionPending = false;
  activities = {};
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
    dispatchPending = false;
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
    return result;
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
      ? "Separate workspaces; shared orchestration is not in use. Click Confirm file transfer at each analyst boundary."
      : "Recorded inputs pass directly to the dependent jobs.",
  );
  render();
};
$("revise-cpue").onclick = () => {
  $("filter").value = $("filter").value === "0" ? "1200" : "0";
  status(
    "",
    "CPUE A needs an update",
    "Run the revised analysis, then pass its output to assessment.",
  );
  selectJob("cpue_a");
};
async function transferFiles(connect = false) {
  if (!waitingTransfer || confirmingTransfer) return;
  confirmingTransfer = true;
  render();
  try {
    await call("transfer", { connect });
    if (connect) $("handover").value = "connected";
    render();
  } catch (error) {
    confirmingTransfer = false;
    status(
      "failed",
      "Transfer not confirmed",
      error.message + " Try the transfer again.",
    );
    render();
  }
}
$("transfer-files").onclick = () => transferFiles();
$("connect-workflow").onclick = () => transferFiles(true);
$("reset").onclick = async () => {
  try {
    const result = await call("reset");
    reproductionChecks.clear();
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
  workspaceView = "jobs";
  jobStatusFilter = "";
  $("task-title").textContent = "All jobs";
  render();
};
$("show-tasks").onclick = () => {
  workspaceView = "tasks";
  render();
};
$("running-jobs").onclick = () => {
  workspaceView = "jobs";
  selectedTask = "";
  jobStatusFilter = "running";
  render();
};
$("task-filter").onchange = () => {
  selectedTask = $("task-filter").value;
  render();
};
$("job-status-filter").onchange = () => {
  jobStatusFilter = $("job-status-filter").value;
  render();
};
for (const icon of document.querySelectorAll("[data-workspace-icon]")) {
  icon.append(lineIcon(icon.dataset.workspaceIcon));
}

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
  if (output.record && !output.comparison) {
    output.comparison = reproductionChecks.get(checkKey(output.record));
  }
  currentOutput = output;
  $("output-title").textContent = title;
  $("output-kind").textContent = kind;
  $("output-frame").srcdoc = output.html;
  $("output-frame").hidden = false;
  $("output-json").hidden = true;
  $("output-record").hidden = true;
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
    const record = button.dataset.output === "record";
    $("output-frame").hidden = !report;
    $("output-record").hidden = !record;
    $("output-json").hidden = report || record;
    if (record) renderRecord();
    else if (!report) {
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

function explainMode() {
  $("mode-help").textContent = mode === "cloud"
    ? "New results on GitHub · Docker."
    : mode === "live"
    ? payload.runtime
      ? "New results here, without internet."
      : "Download Python once; then run here."
    : "Saved results; does not run code.";
}

async function activateMode(next) {
  const version = ++modeVersion;
  ++planVersion;
  modeStates[mode] = {
    records,
    states,
    latestRun,
    selected,
    completedSummary,
    messages: [...messages],
    settings: settings(),
    handover: $("handover").value,
  };
  mode = next;
  explainMode();
  ready = false;
  plan = null;
  waitingTransfer = null;
  correctionPending = false;
  activities = {};
  dispatchPending = false;
  $("mode").value = mode;
  $("github-run").hidden = true;
  const saved = modeStates[mode];
  records = saved?.records || {};
  states = saved?.states || {};
  latestRun = saved?.latestRun || "";
  selected = saved?.selected || "submission";
  $("handover").value = saved?.handover || "connected";
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
    $("snapshot").value = payload.saved.settings.last_year;
    $("filter").value = payload.saved.settings.min_hooks_a;
    $("mortality").value = Number(payload.saved.settings.mortality_2).toFixed(2);
    states = Object.fromEntries(jobs.map((job) => [job.key, "complete"]));
    latestRun = "Saved example";
    messages.length = 0;
    payload.saved.events.forEach(log);
    status(
      "",
      "Saved results",
      "Open a job’s output, or choose a run mode to recalculate.",
    );
  } else {
    status(
      "running",
      mode === "cloud"
        ? "Connecting to the live run"
        : "Preparing Offline run",
      mode === "cloud"
        ? "Checking the live service. You can also choose Offline run."
        : "Preparing the supplied Python code and data.",
    );
    $("offline-fallback").hidden = mode !== "cloud";
    const slowConnection = mode === "cloud" ? setTimeout(() => {
      if (version !== modeVersion || ready) return;
      status("running", "Waiting for the live service",
        "The connection is taking longer than usual. You can choose Offline run instead.");
      $("offline-fallback").hidden = false;
    }, 3000) : null;
    render();
    try {
      if (mode === "cloud" && !cloudReady) {
        await cloud.initialise();
        cloudReady = true;
        if (version !== modeVersion) return;
      }
      if (mode === "live" && !offlineReady) {
        const result = await initialiseOffline();
        if (version !== modeVersion) return;
        records = result.records;
      }
      if (version !== modeVersion) return;
      ready = mode === "cloud" ? cloudReady : offlineReady;
      explainMode();
      status(
        "",
        Object.keys(records).length ? "Your results are still here" : "Ready to run",
        mode === "cloud"
          ? "No login needed. If the live service is unavailable, choose Offline run."
          : "The same Python analysis runs in this browser.",
      );
      await refreshPlan();
    } catch (error) {
      if (version !== modeVersion) return;
      ready = false;
      status(
        "failed",
        mode === "cloud" ? "Live connection unavailable" : "Offline run could not start",
        mode === "cloud"
          ? (error.message === "Failed to fetch"
            ? "The live service could not be reached. Retry or choose Offline run."
            : error.message)
          : error.message + " You can still choose View example to inspect the saved results.",
      );
      $("offline-fallback").hidden = mode !== "cloud";
      $("retry-connection").textContent = mode === "cloud" ? "Retry connection" : "Try Offline run again";
      $("retry-connection").hidden = false;
    } finally {
      clearTimeout(slowConnection);
    }
  }
  $("run-id").textContent = latestRun;
  $("execution-note").textContent = mode === "cloud"
    ? "Live results expire after 10 minutes. Download this run to keep them."
    : mode === "live"
    ? "Results stay in this tab. Download this run to keep them."
    : "Example outputs are included in this HTML file.";
  $("selection-title").textContent = byKey[selected].title;
  $("selection-description").textContent = byKey[selected].description;
  render();
}
$("mode").onchange = () => activateMode($("mode").value);
$("offline-fallback").onclick = () => activateMode("live");
$("retry-connection").onclick = () => activateMode(mode);
if (!payload.runtimeUrl) $("offline-download").hidden = true;
render();
activateMode("cloud");
