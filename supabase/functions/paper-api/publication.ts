type Database = (path: string, method?: string, body?: unknown) => Promise<any>;

/** One database snapshot pairs the latest completed request with its package. */
export async function publishedBundle(db: Database, session: string) {
  const rows = await db("paper_runs?session_id=eq." + session +
    "&order=created_at.desc&limit=1&select=id,status,paper_sessions(bundle)");
  const run = rows[0];
  if (!run || run.status !== "complete" || !run.paper_sessions?.bundle) {
    throw Error("Download after a successful run.");
  }
  return { request_id: run.id, bundle: run.paper_sessions.bundle };
}
