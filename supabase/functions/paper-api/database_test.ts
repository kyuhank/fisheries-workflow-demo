import { createDatabase, DatabaseError } from "./database.ts";

/** Inspect requested deadlines without sleeping or making a network request. */
async function inspectTransport(
  check: (deadlines: number[], diagnostics: unknown[][]) => Promise<void>,
) {
  const timeout = AbortSignal.timeout, log = console.error;
  const deadlines: number[] = [], diagnostics: unknown[][] = [];
  AbortSignal.timeout = (milliseconds: number) => {
    deadlines.push(milliseconds);
    return new AbortController().signal;
  };
  console.error = (...values: unknown[]) => { diagnostics.push(values); };
  try {
    await check(deadlines, diagnostics);
  } finally {
    AbortSignal.timeout = timeout;
    console.error = log;
  }
}

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

Deno.test("an aborted read retries within the ordinary deadline without exposing its error", async () => {
  await inspectTransport(async (deadlines, diagnostics) => {
    let attempts = 0;
    const db = createDatabase(
      "https://private.invalid",
      "private-key",
      async () => {
        attempts++;
        if (attempts === 1) {
          throw new DOMException("private URL and token", "AbortError");
        }
        return Response.json([{ status: "running" }]);
      },
    );
    const rows = await db("paper_runs?id=eq.private-run");
    if (
      attempts !== 2 || rows[0].status !== "running" ||
      JSON.stringify(deadlines) !== "[8000,8000]"
    ) throw Error("The aborted read did not recover within its original bounds.");
    const observed = diagnostics[0]?.[1] as Record<string, unknown>;
    if (
      diagnostics.length !== 1 || observed.class !== "AbortError" ||
      observed.phase !== "run_read" || observed.status !== null ||
      typeof observed.elapsed_ms !== "number" || observed.elapsed_ms < 0 ||
      Object.keys(observed).sort().join(",") !== "class,elapsed_ms,phase,status" ||
      JSON.stringify(diagnostics).includes("private")
    ) throw Error("Read diagnostics exposed data or lost their phase.");
  });
});

Deno.test("a large finish keeps its original bytes and receipt after a lost response", async () => {
  await inspectTransport(async (deadlines, diagnostics) => {
    const operation = "00000000-0000-4000-8000-000000000002";
    const body = {
      p_request: "00000000-0000-4000-8000-000000000001",
      p_operation: operation,
      p_action: "finish",
      p_body: {
        checkpoint: "C".repeat(2_800_000),
        bundle: "B".repeat(2_800_000),
        state: { records: {} },
        result: { run_id: "Run 002" },
        error: null,
        pending_events: [],
      },
    };
    const original = JSON.stringify(body), requests: string[] = [], urls: string[] = [];
    const db = createDatabase(
      "https://private.invalid",
      "private-key",
      async (url, options) => {
        urls.push(String(url));
        requests.push(String(options!.body));
        if (requests.length === 1) {
          // A changed caller object must not mutate an already submitted receipt.
          body.p_body.checkpoint = "private changed checkpoint";
          return new Response("private database response", { status: 503 });
        }
        return Response.json(null);
      },
    );
    const result = await db("rpc/paper_runner_write", "POST", body);
    if (
      result !== null || requests.length !== 2 ||
      requests.some((value) => value !== original) ||
      requests.some((value) => JSON.parse(value).p_operation !== operation) ||
      urls.some((url) => url !== "https://private.invalid/rest/v1/rpc/paper_runner_finish") ||
      JSON.stringify(deadlines) !== "[25000,25000]"
    ) throw Error("Large result custody changed during its receipt retry.");
    const observed = diagnostics[0]?.[1] as Record<string, unknown>;
    if (
      diagnostics.length !== 1 || observed.class !== "HTTPError" ||
      observed.phase !== "runner_finish" || observed.status !== 503 ||
      JSON.stringify(diagnostics).includes("private") ||
      JSON.stringify(diagnostics).includes(operation)
    ) throw Error("Finish diagnostics exposed data or lost their phase.");
    await db("rpc/paper_runner_write", "POST", {
      p_operation: operation,
      p_action: "event",
      p_body: { event: { state: "running" } },
    });
    if (deadlines[2] !== 8000 ||
      urls[2] !== "https://private.invalid/rest/v1/rpc/paper_runner_write") {
      throw Error("The finish path or deadline leaked into ordinary event delivery.");
    }
  });
});

Deno.test("an interrupted finish remains bounded and cannot claim success", async () => {
  await inspectTransport(async (deadlines, diagnostics) => {
    let attempts = 0;
    const failure = new Error("private URL, token and request data");
    failure.name = "private error name";
    const db = createDatabase(
      "https://private.invalid",
      "private-key",
      async () => { attempts++; throw failure; },
    );
    try {
      await db("rpc/paper_runner_write", "POST", {
        p_action: "finish",
        p_operation: "private-operation",
      });
      throw Error("An unacknowledged finish claimed success.");
    } catch (error) {
      if (
        !(error instanceof DatabaseError) || !error.retryable ||
        attempts !== 3 || JSON.stringify(deadlines) !== "[25000,25000,25000]" ||
        error.message !== "The database connection was interrupted."
      ) throw Error("Finish failure bounds or public error changed.");
    }
    if (
      diagnostics.length !== 3 ||
      diagnostics.some((entry) => {
        const value = entry[1] as Record<string, unknown>;
        return value.class !== "OtherError" || value.phase !== "runner_finish" ||
          value.status !== null ||
          Object.keys(value).sort().join(",") !== "class,elapsed_ms,phase,status";
      }) || JSON.stringify(diagnostics).includes("private")
    ) throw Error("An exhausted finish exposed private diagnostic content.");
  });
});

Deno.test("the restricted finish endpoint rejects an event without retries or a larger deadline", async () => {
  await inspectTransport(async (deadlines) => {
    let attempts = 0;
    const db = createDatabase("https://example.invalid", "test-only", async (url) => {
      attempts++;
      if (String(url) !== "https://example.invalid/rest/v1/rpc/paper_runner_finish") {
        throw Error("An invalid finish action escaped the restricted endpoint.");
      }
      return new Response("private SQL rejection", { status: 400 });
    });
    try {
      await db("rpc/paper_runner_finish", "POST", { p_action: "event" });
      throw Error("The restricted RPC accepted an event.");
    } catch (error) {
      if (!(error instanceof DatabaseError) || error.retryable || attempts !== 1 ||
        JSON.stringify(deadlines) !== "[8000]" || error.message.includes("private")) {
        throw Error("The invalid finish action changed its bounds or exposed SQL details.");
      }
    }
  });
});

Deno.test("a direct finish RPC retries only the same acknowledged receipt", async () => {
  await inspectTransport(async (deadlines) => {
    const body = { p_request: "fixed-run", p_operation: "fixed-operation", p_action: "finish", p_body: {} };
    const original = JSON.stringify(body), requests: string[] = [];
    const db = createDatabase("https://example.invalid", "test-only", async (url, options) => {
      if (String(url) !== "https://example.invalid/rest/v1/rpc/paper_runner_finish") {
        throw Error("The direct finish receipt changed endpoints.");
      }
      requests.push(String(options!.body));
      if (requests.length === 1) {
        body.p_operation = "changed caller";
        throw new TypeError("lost response after commit");
      }
      return Response.json(null);
    });
    const result = await db("rpc/paper_runner_finish", "POST", body);
    if (result !== null || requests.length !== 2 || requests.some((r) => r !== original) ||
      JSON.stringify(deadlines) !== "[25000,25000]") {
      throw Error("The direct finish receipt was not repeated safely.");
    }
  });
});
