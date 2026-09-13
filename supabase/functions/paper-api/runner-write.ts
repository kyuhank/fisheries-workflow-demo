/** Only authenticated runners reach this boundary; SQL commits each receipt atomically. */
const uuid = (value: unknown) =>
  typeof value === "string" &&
  /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value);

export function validateRunnerWrite(action: string, body: any, jobs: string[]) {
  if (!body || !uuid(body.operation_id)) {
    throw Error("Invalid operation identifier.");
  }
  if (action === "event") {
    if (
      !body.event || typeof body.event.state !== "string" ||
      (body.event.job && !jobs.includes(body.event.job)) ||
      (body.output &&
        (!jobs.includes(body.event.job) || body.event.state !== "complete"))
    ) throw Error("Invalid job event.");
  } else if (action === "finish") {
    if (
      typeof body.checkpoint !== "string" || typeof body.bundle !== "string" ||
      !body.state || (!body.error && !body.result) ||
      (body.error != null && typeof body.error !== "string") ||
      !Array.isArray(body.pending_events) || body.pending_events.length > 128
    ) throw Error("Invalid completed execution.");
    for (const event of body.pending_events) {
      validateRunnerWrite("event", event, jobs);
    }
  } else throw Error("Unknown runner operation.");
}
