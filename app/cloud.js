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

  async request(path, body, anonymous = false, signal) {
    if (!anonymous && !this.session) {
      throw Object.assign(Error("This temporary session has expired."), {
        sessionUnavailable: true,
      });
    }
    const suffix = anonymous
      ? ""
      : (path.includes("?") ? "&" : "?") + "session=" + this.session.id;
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (!anonymous) headers.Authorization = "Bearer " + this.session.token;
    const response = await fetch(this.url + path + suffix, {
      method: body === undefined ? "GET" : "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: signal || AbortSignal.timeout(30000),
    });
    const value = await response.json();
    if (!response.ok) {
      throw Object.assign(
        Error(value.error || "The online demonstration is unavailable."),
        {
          // The legacy response also rejects the request before any dispatch.
          sessionUnavailable: [400, 410].includes(response.status) &&
            (value.code === "session_expired" ||
              value.error ===
                "This demonstration session is unavailable. Select Start afresh."),
        },
      );
    }
    return value;
  }

  initialise() {
    // Switching modes while connecting must not create duplicate sessions.
    if (!this.initialising) {
      this.initialising = this.connect().finally(() => {
        this.initialising = null;
      });
    }
    return this.initialising;
  }

  async connect() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const info = await this.request(
        "/info",
        undefined,
        true,
        controller.signal,
      );
      if (!info.configured) {
        throw Error("The live service is unavailable.");
      }
      this.session = await this.request(
        "/session",
        {},
        true,
        controller.signal,
      );
      this.records = {};
      this.run = null;
      return { records: {} };
    } catch (error) {
      if (controller.signal.aborted) {
        throw Error("The live service did not respond within 8 seconds.");
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  forgetSession() {
    this.session = null;
    this.records = {};
    this.run = null;
    this.onEvent({ state: "session_expired" });
  }

  plan(start, settings, scope = "workflow") {
    if (!["job", "workflow"].includes(scope) || !this.jobs.some((job) => job.key === start)) {
      throw Error("Select a job and execution scope.");
    }
    const changed = this.jobs.filter((job) => {
      const record = this.records[job.key];
      if (!record) return true;
      if (job.parents.some((parent) => {
        const input = record.inputs?.[parent], saved = this.records[parent];
        return !input || !saved || input.run_id !== saved.run_id ||
          input.checksum !== saved.outputs?.["output.json"];
      })) return true;
      if (job.key === "submission") {
        return record.settings.last_year !== settings.last_year;
      }
      if (job.key === "cpue_a") {
        return record.settings.min_hooks !== settings.min_hooks_a;
      }
      if (["assessment_a2", "assessment_b2"].includes(job.key)) {
        return record.settings.M !== settings.mortality_2;
      }
      if (job.key === "mse_buffered") {
        return (record.settings.buffer ?? 0.8) !== (settings.mse_buffer ?? 0.8);
      }
      return false;
    }).map((job) => job.key);
    const run = new Set();
    if (scope === "job") {
      const required = new Set([start]);
      for (const job of [...this.jobs].reverse()) {
        if (required.has(job.key)) job.parents.forEach((parent) => required.add(parent));
      }
      for (const job of this.jobs) {
        if (required.has(job.key) && (job.key === start || changed.includes(job.key) ||
            job.parents.some((parent) => run.has(parent)))) run.add(job.key);
      }
    } else {
      [start, ...changed].forEach((key) => run.add(key));
      for (const job of this.jobs) {
        if (job.parents.some((parent) => run.has(parent))) run.add(job.key);
      }
    }
    return {
      start,
      scope,
      changed,
      run: this.jobs.filter((job) => run.has(job.key)).map((job) => job.key),
      retained: this.jobs.filter((job) => !run.has(job.key) && this.records[job.key]).map((job) =>
        job.key
      ),
    };
  }

  async dispatch(input) {
    try {
      return await this.request("/run", input);
    } catch (error) {
      if (
        ["TypeError", "AbortError", "TimeoutError", "SyntaxError"].includes(
          error.name,
        )
      ) {
        error.executionUnknown = true;
      }
      throw error;
    }
  }

  async execute(input) {
    if (!this.session) await this.initialise();
    let request;
    try {
      request = await this.dispatch(input);
    } catch (error) {
      if (!error.sessionUnavailable) throw error;
      this.forgetSession();
      await this.initialise();
      // Retry once, only after the server confirms no run was dispatched.
      // Keep the selected job, settings and handover mode unchanged.
      request = await this.dispatch(input);
    }
    let cursor = 0, failures = 0, holdUntil = 0, shownGroup = "";
    const deadline = Date.now() + 10 * 60 * 1000;
    while (Date.now() < deadline) {
      let update;
      try {
        update = await this.request("/state?after=" + cursor);
        failures = 0;
      } catch (error) {
        if (error.sessionUnavailable) throw error;
        if (++failures >= 4) {
          throw Object.assign(
            Error("The connection to the live run was interrupted."),
            { executionUnknown: true },
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
        const group = event.state === "running" && event.group?.length > 1
          ? event.group.join(",")
          : "";
        if (!group || group !== shownGroup) {
          const remaining = holdUntil - performance.now();
          if (remaining > 0) {
            await new Promise((resolve) => setTimeout(resolve, remaining));
          }
        }
        if (event.state === "phase") {
          this.onPhase(event.title, event.message, this.run.github_run);
        } else {
          if (event.record) this.records[event.job] = event.record;
          this.onEvent(event);
        }
        // Keep observed activity readable even when a poll returns several events.
        if (!group || group !== shownGroup) {
          holdUntil = performance.now() +
            (["running", "failed", "returned"].includes(event.state)
              ? 1000
              : 0);
        }
        shownGroup = group;
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
    throw Object.assign(Error("The live run has not reported completion."), {
      executionUnknown: true,
    });
  }

  async call(type, data = {}) {
    try {
      if (type === "plan") return this.plan(data.start, data.settings, data.scope);
      if (type === "run") return await this.execute(data);
      if (type === "view") {
        return await this.request(
          "/output?job=" + encodeURIComponent(data.job),
        );
      }
      if (type === "transfer") return await this.request("/transfer", data);
      if (type === "download") return (await this.request("/bundle")).bundle;
      if (type === "reset") {
        try {
          await this.request("/reset", {});
        } catch (error) {
          if (!error.sessionUnavailable) throw error;
        }
        this.records = {};
        this.session = await this.request("/session", {}, true);
        return { records: {} };
      }
      throw Error("Unknown online operation.");
    } catch (error) {
      if (error.sessionUnavailable) {
        this.forgetSession();
        error.message =
          "The temporary live results have expired. Press Run to rebuild the missing inputs with your selected settings.";
      }
      throw error;
    }
  }
}
