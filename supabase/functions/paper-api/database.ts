/** Retry temporary failures only for reads and repeatable state updates. */
export function createDatabase(url: string, key: string, transport = fetch) {
  return async function db(path: string, method = "GET", body?: unknown) {
    const attempts = ["GET", "PATCH"].includes(method) ? 3 : 1;
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
          signal: AbortSignal.timeout(15000),
        });
      } catch {
        if (attempt + 1 === attempts) {
          throw Error("The database connection was interrupted.");
        }
      }
      if (response?.ok) {
        return response.status === 204 ? null : await response.json();
      }
      if (response) {
        const status = response.status;
        await response.body?.cancel();
        if (
          ![429, 500, 502, 503, 504].includes(status) ||
          attempt + 1 === attempts
        ) {
          throw Error(
            `The database request could not be completed (HTTP ${status}).`,
          );
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }
  };
}
