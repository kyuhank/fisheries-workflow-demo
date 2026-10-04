export class DatabaseError extends Error {
  constructor(message: string, readonly retryable: boolean) {
    super(message);
  }
}

/** Retry reads, repeatable patches and the transactional runner receipt RPC. */
export function createDatabase(url: string, key: string, transport = fetch) {
  return async function db(path: string, method = "GET", body?: unknown) {
    const repeatable = ["GET", "PATCH"].includes(method) ||
      (method === "POST" && path === "rpc/paper_runner_write");
    const attempts = repeatable ? 3 : 1;
    const finish = method === "POST" && path === "rpc/paper_runner_write" &&
      (body as { p_action?: unknown } | undefined)?.p_action === "finish";
    // A finish carries the checkpoint and reproducibility bundle. Give that
    // transport more time; PostgreSQL's own statement/lock limits still apply.
    const deadline = finish ? 25000 : 8000;
    const phase = finish ? "runner_finish"
      : method === "POST" && path === "rpc/paper_runner_write" ? "runner_write"
      : method === "GET" && path.startsWith("paper_runs?") ? "run_read"
      : method === "GET" ? "read" : "write";
    // A caller changing its object while a response is lost must not change
    // the payload associated with the original receipt on a retry.
    const payload = body === undefined ? undefined : JSON.stringify(body);
    for (let attempt = 0; attempt < attempts; attempt++) {
      let response: Response | undefined;
      const started = performance.now();
      try {
        response = await transport(url + "/rest/v1/" + path, {
          method,
          headers: {
            apikey: key,
            Authorization: "Bearer " + key,
            "Content-Type": "application/json",
            Prefer: "return=representation,resolution=merge-duplicates",
          },
          body: payload,
          signal: AbortSignal.timeout(deadline),
        });
        if (response.ok) {
          return response.status === 204 ? null : await response.json();
        }
      } catch (error) {
        const name = error instanceof Error || error instanceof DOMException
          ? error.name : "";
        console.error("Database request failed", {
          class: ["AbortError", "TimeoutError", "TypeError", "SyntaxError"].includes(name)
            ? name : "OtherError",
          phase,
          elapsed_ms: Math.round(performance.now() - started),
          status: response?.status ?? null,
        });
        response = undefined;
        if (attempt + 1 === attempts) {
          throw new DatabaseError(
            "The database connection was interrupted.",
            true,
          );
        }
      }
      if (response) {
        const status = response.status;
        console.error("Database request failed", {
          class: "HTTPError",
          phase,
          elapsed_ms: Math.round(performance.now() - started),
          status,
        });
        await response.body?.cancel();
        const retryable = [429, 500, 502, 503, 504].includes(status);
        if (!retryable || attempt + 1 === attempts) {
          throw new DatabaseError(
            `The database request could not be completed (HTTP ${status}).`,
            retryable,
          );
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }
  };
}
