import { validateRunnerWrite } from "./runner-write.ts";

const operation_id = "00000000-0000-4000-8000-000000000001";
const finish = {
  operation_id,
  checkpoint: "archive",
  bundle: "bundle",
  state: {},
  result: { run_id: "Run 001" },
  error: null,
  pending_events: [],
};
const rejects = (action: string, body: unknown) => {
  try {
    validateRunnerWrite(action, body, ["cpue_a"]);
  } catch {
    return;
  }
  throw Error("An invalid runner write was accepted.");
};

Deno.test("runner writes require stable identifiers and valid jobs", () => {
  rejects("event", { event: { state: "running" } });
  rejects("event", {
    operation_id,
    event: { job: "unknown", state: "complete" },
  });
  rejects("event", {
    operation_id,
    event: { job: "cpue_a", state: "running" },
    output: {},
  });
  validateRunnerWrite("event", {
    operation_id,
    event: { job: "cpue_a", state: "running" },
  }, ["cpue_a"]);
});

Deno.test("finishing requires actual results or a recorded failure", () => {
  rejects("finish", { ...finish, result: null });
  validateRunnerWrite("finish", finish, ["cpue_a"]);
  validateRunnerWrite("finish", {
    ...finish,
    result: null,
    error: "Preparation failed.",
  }, ["cpue_a"]);
});

Deno.test("pending events are validated before a finish transaction starts", () => {
  rejects("finish", {
    ...finish,
    pending_events: [{ event: { state: "running" } }],
  });
  rejects("finish", { ...finish, pending_events: Array(129).fill({}) });
  validateRunnerWrite("finish", {
    ...finish,
    pending_events: [
      { operation_id, event: { job: "cpue_a", state: "complete" }, output: {} },
    ],
  }, ["cpue_a"]);
});
