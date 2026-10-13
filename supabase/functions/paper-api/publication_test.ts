import { observationUpdate } from "./github.ts";
import { publishedBundle } from "./publication.ts";

const session = "00000000-0000-4000-8000-000000000001";
const current = "00000000-0000-4000-8000-000000000002";
const previous = "00000000-0000-4000-8000-000000000003";

function assert(value: unknown, message: string) {
  if (!value) throw Error(message);
}

function equal(actual: unknown, expected: unknown, message: string) {
  assert(
    JSON.stringify(actual) === JSON.stringify(expected),
    message + ": " + JSON.stringify({ actual, expected }),
  );
}

async function rejected(action: () => Promise<unknown>) {
  try {
    await action();
  } catch (error) {
    assert(
      error instanceof Error &&
        error.message === "Download after a successful run.",
      "Unexpected publication error: " + String(error),
    );
    return;
  }
  throw Error("An unpublished package was offered for download");
}

/** Interpret the latest-row ordering and FK object projection in one snapshot. */
function snapshot(rows: any[], bundle: unknown = "current-package") {
  const calls: { path: string; method: string }[] = [];
  return {
    calls,
    async db(path: string, method = "GET") {
      calls.push({ path, method });
      const url = new URL("https://fixture.invalid/" + path);
      assert(
        url.pathname === "/paper_runs" && method === "GET",
        "Publication must only read the run snapshot",
      );
      equal(Object.fromEntries(url.searchParams), {
        session_id: "eq." + session,
        order: "created_at.desc",
        limit: "1",
        select: "id,status,paper_sessions(bundle)",
      }, "Publication did not request a session-scoped latest-row FK snapshot");
      const latest = rows.filter((row) => row.session_id === session)
        .sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 1);
      return latest.map((row) => ({
        id: row.id,
        status: row.status,
        paper_sessions: { bundle },
      }));
    },
  };
}

const run = (
  status: string,
  id = current,
  created_at = "2026-10-13T03:15:00Z",
) => ({
  id,
  session_id: session,
  status,
  created_at,
});

Deno.test("missing, queued, running, handover, failed and expired runs cannot publish a package", async () => {
  for (
    const status of [null, "queued", "running", "handover", "failed", "expired"]
  ) {
    const fixture = snapshot(
      status === null ? [] : [run(status)],
      "older-package",
    );
    await rejected(() => publishedBundle(fixture.db, session));
    assert(
      fixture.calls.length === 1,
      "Publication made more than one snapshot read",
    );
  }
});

Deno.test("the latest completed run publishes its own ID and joined bundle in one read", async () => {
  const fixture = snapshot([
    run("complete", previous, "2026-10-13T03:00:00Z"),
    run("complete"),
  ], "current-package");
  equal(await publishedBundle(fixture.db, session), {
    request_id: current,
    bundle: "current-package",
  }, "Publication did not identify the latest successful snapshot");
  assert(fixture.calls.length === 1, "Run and bundle came from separate reads");
});

Deno.test("a newer failed buffer run blocks the older successful growth package", async () => {
  const fixture = snapshot([
    run("complete", previous, "2026-10-13T03:00:00Z"),
    run("failed"),
  ], "growth-035-package");
  await rejected(() => publishedBundle(fixture.db, session));
  assert(
    fixture.calls.length === 1,
    "Failed-run guard retried another publication read",
  );
});

Deno.test("a newer busy run cannot fall back to a prior complete run", async () => {
  const fixture = snapshot([
    run("complete", previous, "2026-10-13T03:00:00Z"),
    run("running"),
  ], "prior-package");
  await rejected(() => publishedBundle(fixture.db, session));
  assert(fixture.calls.length === 1, "Busy-run guard tried a fallback read");
});

Deno.test("another session's newer run cannot become the publication identity", async () => {
  const fixture = snapshot([
    run("complete"),
    {
      ...run("failed", previous, "2026-10-13T03:30:00Z"),
      session_id: previous,
    },
  ]);
  const result = await publishedBundle(fixture.db, session);
  assert(
    result.request_id === current && fixture.calls.length === 1,
    "Publication crossed the session boundary",
  );
});

Deno.test("an absent, empty or wrong-shaped FK join fails closed", async () => {
  for (
    const joined of [
      undefined,
      null,
      {},
      { bundle: null },
      { bundle: "" },
      [],
      [{ bundle: "wrong-shape-package" }],
    ]
  ) {
    let calls = 0;
    await rejected(() =>
      publishedBundle(async () => {
        calls++;
        return [{ id: current, status: "complete", paper_sessions: joined }];
      }, session)
    );
    assert(calls === 1, "Missing joined bundle triggered another read");
  }
});

Deno.test("database publication failure propagates without a stale fallback", async () => {
  const failure = new Error("simulated snapshot interruption");
  let calls = 0;
  try {
    await publishedBundle(async () => {
      calls++;
      throw failure;
    }, session);
    throw Error("Publication swallowed its database failure");
  } catch (error) {
    assert(
      error === failure && calls === 1,
      "Publication retried or changed the failure",
    );
  }
});

Deno.test("unchanged GitHub queued, running and successful observations require no update", () => {
  for (const status of ["queued", "in_progress", "completed"]) {
    equal(
      observationUpdate({ github_run: "38340681828" }, {
        id: 38340681828,
        status,
        conclusion: status === "completed" ? "success" : null,
      }),
      {},
      "An unchanged observation would acquire a run-row write lock",
    );
  }
  equal(
    observationUpdate({ github_run: "38340681828" }, null),
    {},
    "An absent remote run created an update",
  );
});

Deno.test("new or changed GitHub bindings are persisted without unrelated state", () => {
  for (const github_run of [null, undefined, "different-run"]) {
    equal(
      observationUpdate({ github_run, status: "handover" }, {
        id: 38340681828,
        status: "in_progress",
        conclusion: null,
      }),
      { github_run: "38340681828" },
      "A new binding changed unrelated run state",
    );
  }
});

Deno.test("terminal GitHub failures preserve the binding delta and specific message", () => {
  for (
    const conclusion of ["failure", "cancelled", "timed_out", "action_required"]
  ) {
    const remote = { id: 38340681828, status: "completed", conclusion };
    const failed = {
      status: "failed",
      error: "The GitHub execution " + conclusion +
        ". Open its execution record for details.",
    };
    equal(
      observationUpdate({ github_run: "38340681828" }, remote),
      failed,
      "A terminal failure lost its message or rewrote an unchanged binding",
    );
    equal(observationUpdate({ github_run: null }, remote), {
      github_run: "38340681828",
      ...failed,
    }, "A newly observed failed run lost its binding");
  }
});

Deno.test("observationUpdate is pure and an empty cached delta preserves newer run state", () => {
  const original = {
    id: current,
    github_run: "38340681828",
    status: "running",
  };
  const remote = { id: 38340681828, status: "in_progress", conclusion: null };
  const before = JSON.stringify([original, remote]);
  const delta = observationUpdate(original, remote);
  equal(
    JSON.stringify([original, remote]),
    before,
    "Observation mutated its inputs",
  );
  equal({ ...original, status: "handover", ...delta }, {
    ...original,
    status: "handover",
  }, "An empty cached observation overwrote newer database progress");
});
