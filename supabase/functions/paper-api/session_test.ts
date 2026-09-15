import { checkSession, SessionExpired, startInSession } from "./session.ts";

const now = Date.parse("2026-09-15T00:20:00Z");
const row = (age: number) => ({
  id: "session",
  token_hash: "valid",
  state: { records: {} },
  touched_at: new Date(now - age).toISOString(),
});

Deno.test("missing and idle sessions expire without extending retention", () => {
  for (const rows of [[], [row(10 * 60 * 1000 + 1)]]) {
    try {
      checkSession(rows, "valid", now);
    } catch (error) {
      if (error instanceof SessionExpired) continue;
      throw error;
    }
    throw Error("An expired session was accepted.");
  }
  const recent = row(9 * 60 * 1000);
  if (checkSession([recent], "valid", now) !== recent) {
    throw Error("A current session lost its recorded state.");
  }
});

Deno.test("a current session still requires its matching credential", () => {
  try {
    checkSession([row(0)], "different", now);
  } catch (error) {
    if (!(error instanceof SessionExpired)) return;
  }
  throw Error("An invalid credential was accepted or classified as expiry.");
});

Deno.test("expiry during start is reported without retrying the start", async () => {
  for (const rows of [[], [row(10 * 60 * 1000 + 1)]]) {
    let starts = 0;
    try {
      await startInSession(
        () => {
          starts++;
          return Promise.reject(Error("RPC rejected"));
        },
        () => Promise.resolve(checkSession(rows, "valid", now)),
      );
    } catch (error) {
      if (error instanceof SessionExpired && starts === 1) continue;
      throw error;
    }
    throw Error("The rejected start was not classified as expiry.");
  }
});

Deno.test("successful starts and unrelated failures are never repeated", async () => {
  let checks = 0;
  const result = await startInSession(
    () => Promise.resolve("started"),
    () => {
      checks++;
      return Promise.resolve();
    },
  );
  if (result !== "started" || checks !== 0) {
    throw Error("Unexpected session check.");
  }
  const original = Error("database unavailable or shared limit reached");
  for (
    const validate of [
      () => Promise.resolve(checkSession([row(0)], "valid", now)),
      () => Promise.reject(Error("session lookup unavailable")),
    ]
  ) {
    let starts = 0;
    try {
      await startInSession(
        () => {
          starts++;
          return Promise.reject(original);
        },
        validate,
      );
    } catch (error) {
      if (error === original && starts === 1) continue;
      throw error;
    }
    throw Error("The original failure was lost.");
  }
});
