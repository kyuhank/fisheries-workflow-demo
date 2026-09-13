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
    for (let attempt = 0; attempt < attempts; attempt++) {
      let response: Response | undefined;
      try {
        response = await transport(url + "/rest/v1/" + path, {
          method,
          headers: {
            apikey: key,
            Authorization: "Bearer " + key,
            "Content-Type": "application/json",
            Prefer: "return=representation,resolution=merge-duplicates",
          },
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: AbortSignal.timeout(8000),
        });
        if (response.ok) {
          return response.status === 204 ? null : await response.json();
        }
      } catch {
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
