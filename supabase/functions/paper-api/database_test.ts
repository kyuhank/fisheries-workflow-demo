import { createDatabase, DatabaseError } from "./database.ts";

Deno.test("a timed-out state update retries the same update", async () => {
  const requests: RequestInit[] = [];
  const db = createDatabase(
    "https://example.invalid",
    "test-only",
    async (_url, options) => {
      requests.push(options!);
      return requests.length === 1
        ? new Response("Temporary failure", { status: 504 })
        : Response.json([{ state: "complete" }]);
    },
  );
  const result = await db("paper_sessions?id=eq.example", "PATCH", {
    state: "complete",
  });
  if (
    requests.length !== 2 || result[0].state !== "complete" ||
    requests[0].body !== requests[1].body
  ) {
    throw Error("The state update was not safely repeated.");
  }
});

Deno.test("starting a run is not retried or charged twice", async () => {
  let attempts = 0;
  const db = createDatabase(
    "https://example.invalid",
    "test-only",
    async () => {
      attempts++;
      return new Response("Temporary failure", { status: 504 });
    },
  );
  try {
    await db("rpc/paper_start", "POST", {});
  } catch (error) {
    if (attempts === 1 && String(error).includes("504")) return;
  }
  throw Error("A non-repeatable request was retried or did not fail.");
});

Deno.test("invalid requests are not retried and response bodies stay private", async () => {
  let attempts = 0;
  const db = createDatabase(
    "https://example.invalid",
    "test-only",
    async () => {
      attempts++;
      return new Response("private diagnostic detail", { status: 400 });
    },
  );
  try {
    await db("paper_sessions", "PATCH", {});
  } catch (error) {
    if (
      attempts === 1 && String(error).includes("400") &&
      !String(error).includes("private")
    ) return;
  }
  throw Error("The invalid request was retried or exposed its response.");
});

Deno.test("a runner receipt retries safely after a lost commit response", async () => {
  const bodies: unknown[] = [];
  const db = createDatabase(
    "https://example.invalid",
    "test-only",
    async (_url, options) => {
      bodies.push(options!.body);
      if (bodies.length === 1) throw Error("connection reset after commit");
      return Response.json(null);
    },
  );
  await db("rpc/paper_runner_write", "POST", {
    p_operation: "fixed-operation",
    p_action: "event",
  });
  if (bodies.length !== 2 || bodies[0] !== bodies[1]) {
    throw Error("Receipt changed during retry.");
  }
});

Deno.test("a truncated successful receipt response can be retried", async () => {
  let attempts = 0;
  const db = createDatabase(
    "https://example.invalid",
    "test-only",
    async () => {
      attempts++;
      return attempts === 1
        ? new Response('{"incomplete":')
        : Response.json(null);
    },
  );
  await db("rpc/paper_runner_write", "POST", {
    p_operation: "fixed-operation",
  });
  if (attempts !== 2) throw Error("Truncated response did not retry.");
});

Deno.test("an exhausted database 504 remains distinguishable from invalid input", async () => {
  for (const status of [400, 401, 403, 504]) {
    let attempts = 0;
    const db = createDatabase(
      "https://example.invalid",
      "test-only",
      async () => {
        attempts++;
        return new Response("private database details", { status });
      },
    );
    try {
      await db("rpc/paper_runner_write", "POST", {});
      throw Error("Failure was swallowed.");
    } catch (error) {
      if (
        !(error instanceof DatabaseError) ||
        error.retryable !== (status === 504) ||
        attempts !== (status === 504 ? 3 : 1)
      ) throw Error("Incorrect failure classification.");
    }
  }
});
