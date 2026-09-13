import { createDatabase } from "./database.ts";

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
