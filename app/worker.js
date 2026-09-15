let python;
let transfer = null;
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
    self.postMessage({ type: "event", event });
  });
  python.globals.set("_transfer_js", () => new Promise((resolve) => {
    transfer = resolve;
  }));
  python.runPython(`
import sys, json, base64, shutil
sys.path.insert(0, '/workspace')
from workflow.engine import Workflow
from workflow.spec import SPEC
def _notify(event):
    _notify_js(json.dumps(event))
async def _transfer(handover):
    return await _transfer_js()
runner = Workflow('/runs', notify=_notify, pause=1)
`);
  return JSON.parse(python.runPython("json.dumps(runner.state())"));
}

async function request(type, payload) {
  if (type === "transfer") {
    if (!transfer) throw new Error("No file transfer is pending.");
    const resume = transfer;
    transfer = null;
    resume(Boolean(payload.connect));
    return true;
  }
  if (type === "init") return initialise(payload);
  if (!python) throw new Error("The analysis runtime is still loading.");
  python.globals.set("_request", JSON.stringify(payload || {}));
  python.runPython("request = json.loads(_request)");
  if (type === "plan") {
    return JSON.parse(
      python.runPython(
        'runner.configure(request["settings"]); json.dumps(runner.plan(request["start"], scope=request.get("scope", "workflow")))',
      ),
    );
  }
  if (type === "run") {
    python.runPython(`
runner.configure(request['settings'])
runner.manual_transfer = _transfer if request.get('handover') == 'manual' else None
`);
    return JSON.parse(
      await python.runPythonAsync(
        'json.dumps(await runner.run(request["start"], scope=request.get("scope", "workflow")))',
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
      "shutil.rmtree('/runs', ignore_errors=True); runner = Workflow('/runs', notify=_notify, pause=1)",
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
