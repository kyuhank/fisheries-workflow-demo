type Database = (path: string, method?: string, body?: unknown) => Promise<any>;

/** Confirm one frozen run/boundary; retries cannot confirm a later transfer. */
export async function confirmTransfer(db: Database, session: string, body: any) {
  if (!body || Object.keys(body).sort().join(",") !==
      "connect,request_id,transfer_count" || typeof body.connect !== "boolean" ||
      typeof body.request_id !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(body.request_id) ||
      !Number.isSafeInteger(body.transfer_count) || body.transfer_count < 0) {
    throw Error("Reload the current demo before confirming this file transfer.");
  }
  const target = "paper_runs?id=eq." + body.request_id +
    "&session_id=eq." + session;
  const read = async () => {
    const rows = await db(target + "&select=id,status,transfer_count,connected");
    if (rows.length !== 1) throw Error("This file transfer does not belong to the current session.");
    return rows[0];
  };
  const receipt = (run: any, replay: boolean) => ({
    ok: true, request_id: body.request_id,
    transfer_count: run.transfer_count, connected: run.connected === true, replay,
  });
  let run = await read();
  if (run.transfer_count > body.transfer_count) return receipt(run, true);
  if (run.status !== "handover" || run.transfer_count !== body.transfer_count) {
    throw Error("This file transfer is not pending. Wait for the current run status.");
  }
  const changed = await db(target + "&status=eq.handover&transfer_count=eq." +
    body.transfer_count, "PATCH", {
      transfer_count: body.transfer_count + 1,
      connected: body.connect, status: "running",
    });
  if (Array.isArray(changed) && changed.length === 1) return receipt(changed[0], false);
  // A repeatable PATCH may have committed before its response was lost.
  run = await read();
  if (run.transfer_count > body.transfer_count) return receipt(run, true);
  throw Error("The file transfer was not confirmed. Retry the same transfer.");
}
