let python;
let handoverMode = "connected", activePlan = [], transfer = null;
const transferred = new Set();
const decode = (text) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));

async function initialise(payload) {
  const assets = payload.runtime;
  const script = (name) =>
    URL.createObjectURL(
      new Blob([decode(assets[name])], { type: "text/javascript" }),
    );
  self.fetch = async (input) => {
    const url = typeof input === "string"
      ? input
      : (input.url || String(input));
    const name = url.split("/").pop();
    if (!Object.hasOwn(assets, name)) {
      throw new Error("The preserved runtime does not contain " + name);
    }
    return new Response(decode(assets[name]), {
      headers: {
        "Content-Type": name.endsWith(".wasm")
          ? "application/wasm"
          : "application/octet-stream",
      },
    });
  };
  importScripts(script("pyodide.asm.js"));
  importScripts(script("pyodide.js"));
  python = await loadPyodide({
    indexURL: "https://preserved.invalid/",
    lockFileURL: "https://preserved.invalid/pyodide-lock.json",
    stdout: () => {},
    stderr: (text) => console.warn(text),
  });
  await python.loadPackage("sqlite3");
  for (const [name, content] of Object.entries(payload.files)) {
    const path = "/workspace/" + name;
    python.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
    python.FS.writeFile(path, decode(content));
  }
  python.globals.set("_notify_js", (text) => {
    const event = JSON.parse(text);
    if (event.state === "plan") {
      activePlan = event.run;
      transferred.clear();
    }
    self.postMessage({ type: "event", event });
  });
  python.globals.set("_before_job_js", async (key) => {
    if (handoverMode !== "manual") return "";
    const boundary =
      ["cpue_a", "cpue_b"].includes(key) && activePlan.includes("extract")
        ? "data"
        : key.startsWith("prepare_") &&
            activePlan.some((job) =>
              ["extract", "cpue_a", "cpue_b"].includes(job)
            )
        ? "cpue"
        : null;
    if (!boundary || transferred.has(boundary)) return "";
    const message = boundary === "data"
      ? "The extract is ready. The CPUE analyst is waiting for the selected records."
      : "The CPUE outputs are ready. The assessment analyst is waiting for the indices and their preparation details.";
    self.postMessage({
      type: "event",
      event: { job: key, state: "handover", boundary, message },
    });
    await new Promise((resolve) => {
      transfer = resolve;
    });
    transferred.add(boundary);
    return boundary === "data"
      ? "Manual handover: selected records transferred to CPUE analysis."
      : "Manual handover: CPUE outputs transferred for assessment input preparation.";
  });
  python.runPython(`
import sys, json, base64, shutil
sys.path.insert(0, '/workspace')
from workflow.engine import Workflow
from workflow.spec import SPEC
def _notify(event):
    _notify_js(json.dumps(event))
async def _before_job(key):
    message = await _before_job_js(key)
    if message:
        await runner.emit(key, 'received', message)
runner = Workflow('/runs', notify=_notify, pause=0.7, before_job=_before_job)
`);
  return JSON.parse(python.runPython("json.dumps(runner.state())"));
}

async function request(type, payload) {
  if (type === "transfer") {
    if (!transfer) throw new Error("No file transfer is pending.");
    if (payload.connect) handoverMode = "connected";
    const resume = transfer;
    transfer = null;
    resume();
    return true;
  }
  if (type === "init") return initialise(payload);
  if (!python) throw new Error("The analysis runtime is still loading.");
  python.globals.set("_request", JSON.stringify(payload || {}));
  python.runPython("request = json.loads(_request)");
  if (type === "plan") {
    return JSON.parse(
      python.runPython(
        'runner.configure(request["settings"]); json.dumps(runner.plan(request["start"]))',
      ),
    );
  }
  if (type === "run") {
    handoverMode = payload.handover || "connected";
    python.runPython('runner.configure(request["settings"])');
    return JSON.parse(
      await python.runPythonAsync(
        'json.dumps(await runner.run(request["start"]))',
      ),
    );
  }
  if (type === "view") {
    return JSON.parse(python.runPython(`
key = request['job']
assert key in SPEC
json.dumps({'html': (runner.directory/key/'report.html').read_text(), 'record':runner.records[key], 'output':runner.output(key)})
`));
  }
  if (type === "download") {
    return python.runPython("base64.b64encode(runner.bundle()).decode()");
  }
  if (type === "reset") {
    python.runPython(
      "shutil.rmtree('/runs', ignore_errors=True); runner = Workflow('/runs', notify=_notify, pause=0.7, before_job=_before_job)",
    );
    return JSON.parse(python.runPython("json.dumps(runner.state())"));
  }
  throw new Error("Unknown request.");
}

self.onmessage = async ({ data: { id, type, payload } }) => {
  try {
    self.postMessage({
      id,
      type: "response",
      value: await request(type, payload),
    });
  } catch (error) {
    self.postMessage({ id, type: "error", error: String(error) });
  }
};
