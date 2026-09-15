import { runScope, runSettings } from "./request.ts";

const body = {
  start: "submission",
  handover: "connected",
  settings: { last_year: 2023, min_hooks_a: 0, mortality_2: .3 },
};
const jobs = ["submission", "mse_report"];

Deno.test("execution scope defaults to workflow and stays outside analysis settings", () => {
  if (runScope(body) !== "workflow") throw Error("Legacy run scope changed.");
  for (const scope of ["workflow", "job"]) {
    const scoped = { ...body, scope };
    if (runScope(scoped) !== scope) throw Error("Run scope changed.");
    if (
      JSON.stringify(runSettings(scoped, jobs)) !==
        JSON.stringify(body.settings)
    ) {
      throw Error("Run scope changed the analysis settings.");
    }
    const mse = {
      ...scoped,
      start: "mse_report",
      settings: { ...body.settings, mse: true, mse_buffer: .8 },
    };
    if (runScope(mse) !== scope || runSettings(mse, jobs).mse !== true) {
      throw Error("MSE run scope changed.");
    }
  }
});

Deno.test("execution scope accepts only the two supplied choices", () => {
  for (
    const scope of [
      "",
      "all",
      "JOB",
      null,
      undefined,
      true,
      false,
      0,
      1,
      [],
      {},
    ]
  ) {
    let rejected = false;
    try {
      runSettings({ ...body, scope }, jobs);
    } catch {
      rejected = true;
    }
    if (!rejected) throw Error("Invalid execution scope accepted.");
  }
  for (
    const invalid of [
      { ...body, scope: "job", command: "anything" },
      { ...body, scope: "job", settings: { ...body.settings, scope: "job" } },
      { ...body, scope: "job", start: "mse_report" },
    ]
  ) {
    let rejected = false;
    try {
      runSettings(invalid, jobs);
    } catch {
      rejected = true;
    }
    if (!rejected) throw Error("Scope weakened the request allowlist.");
  }
});

Deno.test("old downloads retain assessment-only execution; current demos include MSE", () => {
  const legacy = runSettings(body, jobs);
  if ("mse" in legacy || "mse_buffer" in legacy) {
    throw Error("Legacy request changed.");
  }
  const extended = {
    ...body,
    start: "mse_report",
    settings: { ...body.settings, mse: true },
  };
  const current = runSettings(extended, jobs);
  if (current.mse !== true) throw Error("MSE was lost.");
  if ("mse_buffer" in current) throw Error("Legacy buffer setting changed.");
  if (
    runSettings({
      ...body,
      settings: { ...body.settings, mse: false },
    }, jobs).mse !== false
  ) throw Error("Assessment-only execution was lost.");
});

Deno.test("supported numeric buffers survive with either MSE flag", () => {
  for (const mse of [false, true]) {
    for (const mse_buffer of [.6, .8, 1]) {
      const settings = runSettings({
        ...body,
        start: mse ? "mse_report" : "submission",
        settings: { ...body.settings, mse, mse_buffer },
      }, jobs);
      if (settings.mse !== mse || settings.mse_buffer !== mse_buffer) {
        throw Error("MSE settings changed.");
      }
    }
  }
});

Deno.test("MSE does not open arbitrary jobs or analysis settings", () => {
  for (
    const invalid of [
      null,
      {},
      { ...body, start: "shell" },
      { ...body, command: "anything" },
      { ...body, start: "mse_report" },
      {
        ...body,
        start: "mse_report",
        settings: { ...body.settings, mse: false, mse_buffer: .8 },
      },
      { ...body, settings: { ...body.settings, mse: "true" } },
      { ...body, settings: { ...body.settings, mse_buffer: .8 } },
      { ...body, settings: { ...body.settings, seed: 3 } },
      {
        ...body,
        settings: { ...body.settings, mse: true, mse_buffer: .8, seed: 3 },
      },
      { ...body, settings: { ...body.settings, mortality_2: -1 } },
      ...[
        true,
        false,
        null,
        undefined,
        "0.8",
        .7,
        0,
        -1,
        1.1,
        NaN,
        Infinity,
        [],
        {},
      ].map(
        (mse_buffer) => ({
          ...body,
          settings: { ...body.settings, mse: true, mse_buffer },
        }),
      ),
    ]
  ) {
    let rejected = false;
    try {
      runSettings(invalid, jobs);
    } catch {
      rejected = true;
    }
    if (!rejected) throw Error("Invalid request accepted.");
  }
});
