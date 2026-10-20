import { finishReceipt } from "./finish-receipt.ts";
import { createDatabase, DatabaseError } from "./database.ts";

const id = "00000000-0000-4000-8000-000000000001";
const operation = "00000000-0000-4000-8000-000000000002";
const request = new Request("https://example.invalid/runner/finish-receipt", {
  headers: { Authorization: "Bearer test-only" },
});

Deno.test("finish receipt authenticates the exact terminal runner before its read-only RPC", async () => {
  const calls: unknown[][] = [];
  const receipt = { request_id: id, operation_id: operation, status: "complete" };
  const value = await finishReceipt(request, id, operation,
    (received, run, finishing) => {
      calls.push([received, run, finishing]);
      return Promise.resolve({ id, status: "complete" });
    },
    (path, method, body) => {
      if (calls.length !== 1 || calls[0][0] !== request ||
          calls[0][1] !== id || calls[0][2] !== true) {
        throw Error("Receipt lookup bypassed the original terminal runner guard.");
      }
      calls.push([path, method, body]);
      return Promise.resolve(receipt);
    });
  if (value.receipt !== receipt || calls.length !== 2 ||
      calls[1][0] !== "rpc/paper_runner_finish_receipt" || calls[1][1] !== "POST" ||
      JSON.stringify(calls[1][2]) !== JSON.stringify({ p_request: id, p_operation: operation })) {
    throw Error("The lookup did not retain its exact request/operation or used a finish body.");
  }
});

Deno.test("a rejected original runner never reaches receipt storage", async () => {
  for (const message of ["Runner identity required.", "Different code version.",
    "Different run identity.", "Run expired.", "Untrusted runner."]) {
    let reads = 0;
    try {
      await finishReceipt(request, id, operation,
        (_request, _id, finishing) => {
          if (!finishing) throw Error("Missing terminal guard.");
          throw Error(message);
        },
        () => { reads++; return Promise.resolve(null); });
    } catch (error) {
      if (reads === 0 && error instanceof Error && error.message === message) continue;
      throw error;
    }
    throw Error("A rejected runner reached a receipt lookup.");
  }
});

Deno.test("receipt lookup requires GET and one explicit UUID, never latest receipt", async () => {
  for (const [method, selected] of [["GET", ""], ["GET", "latest"],
    ["GET", operation + "&operation_id=other"], ["POST", operation]]) {
    let calls = 0;
    try {
      await finishReceipt(new Request(request.url, { method }), id, selected,
        () => { calls++; return Promise.resolve({}); },
        () => { calls++; return Promise.resolve(null); });
    } catch {
      if (calls === 0) continue;
    }
    throw Error("An invalid method or ambiguous operation reached the runner/database.");
  }
  const absent = await finishReceipt(request, id, operation,
    () => Promise.resolve({ status: "complete" }), () => Promise.resolve(null));
  if (absent.receipt !== null) throw Error("Terminal status replaced a missing receipt.");
});

Deno.test("the small read-only receipt RPC has one transport attempt on failure", async () => {
  let attempts = 0;
  const db = createDatabase("https://example.invalid", "test-only", () => {
    attempts++;
    return Promise.resolve(new Response("private failure", { status: 504 }));
  });
  try {
    await finishReceipt(request, id, operation, () => Promise.resolve({}), db);
  } catch (error) {
    if (error instanceof DatabaseError && error.retryable && attempts === 1) return;
    throw error;
  }
  throw Error("A receipt probe was retried or its failure was hidden.");
});
