import { createDatabase, DatabaseError } from "./database.ts";
import { confirmTransfer } from "./transfer.ts";

const session = "00000000-0000-4000-8000-000000000001";
const request = "00000000-0000-4000-8000-000000000002";
const other = "00000000-0000-4000-8000-000000000003";

function assert(value: unknown, message: string): asserts value {
  if (!value) throw Error(message);
}

function equal(actual: unknown, expected: unknown, message: string) {
  assert(
    JSON.stringify(actual) === JSON.stringify(expected),
    message + ": " + JSON.stringify({ actual, expected }),
  );
}

async function rejects(action: () => Promise<unknown>, text: string) {
  try {
    await action();
  } catch (error) {
    assert(
      error instanceof Error && error.message.includes(text),
      "Unexpected rejection: " + String(error),
    );
    return;
  }
  throw Error("Expected rejection containing: " + text);
}

type Run = {
  id: string;
  session_id: string;
  status: string;
  transfer_count: number;
  connected: boolean;
};
type Call = { path: string; method: string; body?: unknown };

/** Apply the request's actual equality filters to an in-memory row. No network. */
function database(overrides: Partial<Run> = {}) {
  const run: Run = {
    id: request,
    session_id: session,
    status: "handover",
    transfer_count: 0,
    connected: false,
    ...overrides,
  };
  const calls: Call[] = [];
  let updates = 0;
  const fixture = {
    run,
    calls,
    get updates() {
      return updates;
    },
    afterRead: undefined as (() => Promise<void>) | undefined,
    beforePatch: undefined as (() => void) | undefined,
    patchRepresentation: true,
    async db(path: string, method = "GET", body?: unknown) {
      calls.push({ path, method, body });
      const url = new URL("https://fixture.invalid/" + path);
      assert(url.pathname === "/paper_runs", "Unexpected database table");
      if (method === "PATCH") fixture.beforePatch?.();
      const matches = [...url.searchParams.entries()]
        .filter(([field]) => field !== "select")
        .every(([field, filter]) => {
          assert(
            field in run && filter.startsWith("eq."),
            "Unexpected or non-equality database filter",
          );
          return String(run[field as keyof Run]) === filter.slice(3);
        });
      if (method === "GET") {
        const selected = url.searchParams.get("select")?.split(",");
        assert(selected !== undefined, "Run read must declare its fields");
        const rows = matches
          ? [
            Object.fromEntries(
              selected.map((field) => [field, run[field as keyof Run]]),
            ),
          ]
          : [];
        await fixture.afterRead?.();
        return rows;
      }
      assert(method === "PATCH", "Unexpected database method");
      if (!matches) return [];
      Object.assign(run, body);
      updates++;
      return fixture.patchRepresentation ? [{ ...run }] : [];
    },
  };
  return fixture;
}

const confirmation = (connect = false, count = 0, id = request) => ({
  connect,
  request_id: id,
  transfer_count: count,
});

/** The injected transport has no live connection that needs a deadline timer. */
async function withoutDeadlineTimers(check: () => Promise<void>) {
  const timeout = AbortSignal.timeout;
  AbortSignal.timeout = () => new AbortController().signal;
  try {
    await check();
  } finally {
    AbortSignal.timeout = timeout;
  }
}

Deno.test("confirmation requires the complete frozen envelope before any database access", async () => {
  const invalid: unknown[] = [
    null,
    undefined,
    false,
    [],
    {},
    { connect: false },
    { request_id: request, transfer_count: 0 },
    { connect: false, transfer_count: 0 },
    { ...confirmation(), additional: true },
    { ...confirmation(), connect: "false" },
    { ...confirmation(), connect: 0 },
    { ...confirmation(), request_id: "not-a-run" },
    { ...confirmation(), request_id: request + "&session_id=eq." + other },
    ...[-1, 0.5, "0", null, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]
      .map((transfer_count) => ({ ...confirmation(), transfer_count })),
  ];
  for (const body of invalid) {
    const fixture = database();
    await rejects(() => confirmTransfer(fixture.db, session, body), "Reload");
    equal(fixture.calls, [], "Malformed confirmation touched the database");
  }
});

Deno.test("a missing run and a run owned by another session cannot be confirmed", async () => {
  for (
    const [fixture, sid, id] of [
      [database(), other, request],
      [database(), session, other],
      [database({ session_id: other }), session, request],
    ] as const
  ) {
    await rejects(
      () => confirmTransfer(fixture.db, sid, confirmation(false, 0, id)),
      "does not belong",
    );
    assert(
      fixture.updates === 0 && fixture.calls.length === 1,
      "An unowned run was modified",
    );
  }
});

Deno.test("a future boundary is rejected without changing the pending transfer", async () => {
  const fixture = database({ transfer_count: 2 });
  await rejects(
    () => confirmTransfer(fixture.db, session, confirmation(false, 3)),
    "not pending",
  );
  assert(
    fixture.run.transfer_count === 2 && fixture.run.status === "handover" &&
      fixture.updates === 0,
    "Future confirmation changed the run",
  );
});

Deno.test("one pending boundary uses an exact run, session, status and count compare-and-swap", async () => {
  const fixture = database({ transfer_count: 7 });
  const receipt = await confirmTransfer(
    fixture.db,
    session,
    confirmation(false, 7),
  );
  equal(receipt, {
    ok: true,
    request_id: request,
    transfer_count: 8,
    connected: false,
    replay: false,
  }, "Incorrect successful confirmation receipt");
  const patch = fixture.calls.find((call) => call.method === "PATCH")!;
  const filters = Object.fromEntries(
    new URL("https://fixture.invalid/" + patch.path).searchParams,
  );
  equal(filters, {
    id: "eq." + request,
    session_id: "eq." + session,
    status: "eq.handover",
    transfer_count: "eq.7",
  }, "The pending boundary was not atomically scoped");
  equal(
    patch.body,
    { transfer_count: 8, connected: false, status: "running" },
    "Confirmation wrote unrelated state",
  );
  assert(fixture.updates === 1, "Confirmation did not update exactly once");
});

Deno.test("double confirmation increments only once, including after the next handover is visible", async () => {
  const fixture = database();
  await confirmTransfer(fixture.db, session, confirmation());
  const repeated = await confirmTransfer(fixture.db, session, confirmation());
  assert(
    repeated.replay && fixture.run.transfer_count === 1 &&
      fixture.updates === 1,
    "Double confirmation advanced the boundary twice",
  );
  fixture.run.status = "handover";
  const delayed = await confirmTransfer(fixture.db, session, confirmation());
  assert(
    delayed.replay && fixture.run.transfer_count === 1 &&
      fixture.run.status === "handover" && fixture.updates === 1,
    "An old delayed retry acknowledged the newer unseen boundary",
  );
  await confirmTransfer(fixture.db, session, confirmation(false, 1));
  equal(
    [fixture.run.transfer_count, fixture.updates],
    [2, 2],
    "A fresh confirmation did not acknowledge its own boundary",
  );
});

Deno.test("stale connect requests return actual connection state without connecting a newer boundary", async () => {
  for (const connected of [false, true]) {
    const fixture = database({ transfer_count: 3, connected });
    const receipt = await confirmTransfer(
      fixture.db,
      session,
      confirmation(!connected, 1),
    );
    assert(
      receipt.replay && receipt.connected === connected &&
        receipt.transfer_count === 3 && fixture.updates === 0 &&
        fixture.run.status === "handover",
      "A stale request changed or misreported the actual connection state",
    );
  }
});

Deno.test("connecting a pending boundary is idempotent and replay reports the stored value", async () => {
  const fixture = database();
  const first = await confirmTransfer(fixture.db, session, confirmation(true));
  const repeated = await confirmTransfer(
    fixture.db,
    session,
    confirmation(true),
  );
  const changedIntent = await confirmTransfer(
    fixture.db,
    session,
    confirmation(false),
  );
  assert(
    first.connected && !first.replay && repeated.connected && repeated.replay &&
      changedIntent.connected && changedIntent.replay && fixture.updates === 1,
    "A replay changed or misreported the committed connection choice",
  );
});

Deno.test("queued, running and terminal states cannot be newly acknowledged or revived", async () => {
  for (const status of ["queued", "running", "complete", "failed", "expired"]) {
    const fixture = database({ status });
    await rejects(
      () => confirmTransfer(fixture.db, session, confirmation(true)),
      "not pending",
    );
    assert(
      fixture.run.status === status && !fixture.run.connected &&
        fixture.updates === 0,
      "A non-pending run was revived",
    );
  }
});

Deno.test("a historical acknowledgement can replay on a terminal run without reviving it", async () => {
  for (const status of ["complete", "failed", "expired"]) {
    const fixture = database({ status, transfer_count: 1, connected: true });
    const receipt = await confirmTransfer(fixture.db, session, confirmation());
    assert(
      receipt.replay && receipt.connected && fixture.updates === 0 &&
        fixture.run.status === status,
      "A terminal replay revived or modified the run",
    );
  }
});

Deno.test("concurrent confirmations of one boundary have one winner and one consistent replay", async () => {
  const fixture = database();
  let release!: () => void, reads = 0;
  const bothRead = new Promise<void>((resolve) => {
    release = resolve;
  });
  fixture.afterRead = async () => {
    if (++reads === 2) release();
    if (reads <= 2) await bothRead;
  };
  const receipts = await Promise.all([
    confirmTransfer(fixture.db, session, confirmation(true)),
    confirmTransfer(fixture.db, session, confirmation(false)),
  ]);
  assert(
    fixture.updates === 1 && fixture.run.transfer_count === 1,
    "Concurrent confirmations both advanced the boundary",
  );
  assert(
    receipts.filter((receipt) => !receipt.replay).length === 1 &&
      receipts.every((receipt) =>
        receipt.connected === fixture.run.connected &&
        receipt.transfer_count === 1
      ),
    "Concurrent receipts disagree with committed state",
  );
});

Deno.test("a run becoming terminal between read and PATCH fails closed", async () => {
  const fixture = database();
  fixture.beforePatch = () => {
    fixture.run.status = "failed";
  };
  await rejects(
    () => confirmTransfer(fixture.db, session, confirmation(true)),
    "not confirmed",
  );
  assert(
    fixture.run.status === "failed" && fixture.run.transfer_count === 0 &&
      !fixture.run.connected && fixture.updates === 0,
    "The compare-and-swap revived a concurrent terminal state",
  );
});

Deno.test("an empty PATCH representation is reconciled only against the original boundary", async () => {
  const fixture = database();
  fixture.patchRepresentation = false;
  const receipt = await confirmTransfer(fixture.db, session, confirmation());
  assert(
    receipt.replay && fixture.updates === 1 && receipt.transfer_count === 1,
    "An empty response did not reconcile the committed boundary",
  );
  const failed = database();
  failed.beforePatch = () => {
    failed.run.status = "running";
  };
  await rejects(
    () => confirmTransfer(failed.db, session, confirmation()),
    "not confirmed",
  );
  assert(
    failed.updates === 0 && failed.run.transfer_count === 0,
    "An empty unmatched PATCH incorrectly claimed confirmation",
  );
});

/** Exercise the actual retrying transport with a fixture rather than HTTP. */
Deno.test("a lost committed PATCH response retries exact bytes and reconciles without a second increment", () =>
  withoutDeadlineTimers(async () => {
    const fixture = database();
    const patches: { url: string; body: string; prefer: string | null }[] = [];
    const db = createDatabase(
      "https://fixture.invalid",
      "test-only",
      async (url, options) => {
        const method = options?.method || "GET";
        const path = String(url).split("/rest/v1/")[1];
        const body = options?.body
          ? JSON.parse(String(options.body))
          : undefined;
        const result = await fixture.db(path, method, body);
        if (method === "PATCH") {
          patches.push({
            url: String(url),
            body: String(options!.body),
            prefer: new Headers(options!.headers).get("Prefer"),
          });
          if (patches.length === 1) {
            fixture.run.status = "handover"; // The worker reached the next boundary before retry.
            throw new TypeError("simulated lost commit response");
          }
        }
        return Response.json(result);
      },
    );
    const receipt = await confirmTransfer(db, session, confirmation());
    assert(
      receipt.replay && fixture.updates === 1 &&
        fixture.run.transfer_count === 1 &&
        fixture.run.status === "handover",
      "Lost-response retry confirmed the newer boundary",
    );
    assert(patches.length === 2, "Lost PATCH response was not retried");
    equal(
      patches[0],
      patches[1],
      "A database retry changed its original request",
    );
    assert(
      patches[0].prefer?.includes("return=representation"),
      "The successful PATCH cannot return its committed representation",
    );
  }));

Deno.test("exhausted lost PATCH responses preserve an error and a later exact replay recovers", () =>
  withoutDeadlineTimers(async () => {
    const fixture = database();
    let patches = 0;
    const db = createDatabase(
      "https://fixture.invalid",
      "test-only",
      async (url, options) => {
        const method = options?.method || "GET";
        const result = await fixture.db(
          String(url).split("/rest/v1/")[1],
          method,
          options?.body ? JSON.parse(String(options.body)) : undefined,
        );
        if (method === "PATCH") {
          patches++;
          throw new TypeError("simulated unacknowledged commit");
        }
        return Response.json(result);
      },
    );
    try {
      await confirmTransfer(db, session, confirmation(true));
      throw Error("An exhausted PATCH response incorrectly claimed success");
    } catch (error) {
      assert(
        error instanceof DatabaseError && error.retryable && patches === 3,
        "An interrupted confirmation lost its transport classification",
      );
    }
    fixture.run.status = "handover";
    const receipt = await confirmTransfer(db, session, confirmation(true));
    assert(
      receipt.replay && receipt.connected && fixture.updates === 1 &&
        patches === 3 &&
        fixture.run.status === "handover",
      "Recovery replay changed the newer boundary",
    );
  }));
