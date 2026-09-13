/** Anonymous reader sessions. The server alone holds the GitHub App credential. */
class CloudRun {
  constructor(config, jobs, onEvent, onPhase) {
    this.url = config.url;
    this.jobs = jobs;
    this.onEvent = onEvent;
    this.onPhase = onPhase;
    this.records = {};
    this.session = null;
  }

  async request(path, body, anonymous = false) {
    const suffix = anonymous
      ? ""
      : (path.includes("?") ? "&" : "?") + "session=" + this.session.id;
    const headers = { "Content-Type": "application/json" };
    if (!anonymous) headers.Authorization = "Bearer " + this.session.token;
    const response = await fetch(this.url + path + suffix, {
      method: body === undefined ? "GET" : "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    });
    const value = await response.json();
    if (!response.ok) {
      throw Error(value.error || "The online demonstration is unavailable.");
    }
    return value;
  }

  async initialise() {
    const info = await this.request("/info", undefined, true);
    if (!info.configured) {
      throw Error(
        "Online execution is not connected yet. Select Offline calculation to run the same analysis here.",
      );
    }
    this.session = await this.request("/session", {}, true);
    return { records: {} };
  }

  plan(start, settings) {
    const changed = this.jobs.filter((job) => {
      const record = this.records[job.key];
      if (!record) return true;
      if (job.key === "submission") {
        return record.settings.last_year !== settings.last_year;
      }
      if (job.key === "cpue_a") {
        return record.settings.min_hooks !== settings.min_hooks_a;
      }
      if (["assessment_a2", "assessment_b2"].includes(job.key)) {
        return record.settings.M !== settings.mortality_2;
      }
      return false;
    }).map((job) => job.key);
    const run = new Set([start, ...changed]);
    for (const job of this.jobs) {
      if (job.parents.some((parent) => run.has(parent))) run.add(job.key);
    }
    return {
      start,
      changed,
      run: this.jobs.filter((job) => run.has(job.key)).map((job) => job.key),
      retained: this.jobs.filter((job) => !run.has(job.key)).map((job) =>
        job.key
      ),
    };
  }

  async execute(input) {
    const request = await this.request("/run", input);
    let cursor = 0, failures = 0;
    const deadline = Date.now() + 10 * 60 * 1000;
    while (Date.now() < deadline) {
      let update;
      try {
        update = await this.request("/state?after=" + cursor);
        failures = 0;
      } catch (error) {
        if (++failures >= 4) {
          throw Error(
            "The connection was interrupted. The GitHub run may still be active; try checking it again shortly.",
          );
        }
        this.onPhase(
          "Reconnecting",
          "The execution continues while its status is reconnected.",
        );
        await new Promise((resolve) => setTimeout(resolve, 1500));
        continue;
      }
      if (!update.run || update.run.id !== request.id) {
        throw Error(
          "This temporary run has expired. Start a new session to continue.",
        );
      }
      this.run = update.run;
      if (this.run.github_run) this.onPhase(null, null, this.run.github_run);
      for (const row of update.events) {
        cursor = row.id;
        const event = row.event;
        if (event.state === "phase") {
          this.onPhase(event.title, event.message, this.run.github_run);
        } else {
          if (event.record) this.records[event.job] = event.record;
          this.onEvent(event);
          // Preserve the order of observed QC/transfer events when a poll returns a batch.
          await new Promise((resolve) =>
            setTimeout(
              resolve,
              event.state === "failed" || event.state === "returned"
                ? 650
                : 120,
            )
          );
        }
      }
      if (["complete", "failed", "expired"].includes(this.run.status)) {
        if (update.state?.records) this.records = update.state.records;
        if (this.run.status !== "complete") {
          throw Error(
            this.run.error || "The online execution ended before completing.",
          );
        }
        return this.run.result;
      }
      if (!cursor) {
        this.onPhase(
          "Waiting for the runner",
          "GitHub is preparing a free runner. Calculations begin when it is ready.",
          this.run.github_run,
        );
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw Error(
      "The online execution timed out. Start a new session or use Offline calculation.",
    );
  }

  async call(type, data = {}) {
    if (type === "plan") return this.plan(data.start, data.settings);
    if (type === "run") return this.execute(data);
    if (type === "view") {
      return this.request("/output?job=" + encodeURIComponent(data.job));
    }
    if (type === "transfer") return this.request("/transfer", data);
    if (type === "download") return (await this.request("/bundle")).bundle;
    if (type === "reset") {
      try {
        await this.request("/reset", {});
      } catch (error) {
        if (!error.message.includes("session is unavailable")) throw error;
      }
      this.records = {};
      this.session = await this.request("/session", {}, true);
      return { records: {} };
    }
    throw Error("Unknown online operation.");
  }
}
