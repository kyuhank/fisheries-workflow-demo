import { runSettings } from "./request.ts";

const body = {
  start: "submission",
  handover: "connected",
  settings: { last_year: 2023, min_hooks_a: 0, mortality_2: .3 },
};
const jobs = ["submission", "mse_report"];

Deno.test("old downloads retain assessment-only execution; current demos include MSE", () => {
  if ("mse" in runSettings(body, jobs)) {
    throw Error("Legacy request changed.");
  }
  const extended = {
    ...body,
    start: "mse_report",
    settings: { ...body.settings, mse: true },
  };
  if (runSettings(extended, jobs).mse !== true) throw Error("MSE was lost.");
});

Deno.test("MSE does not open arbitrary jobs or analysis settings", () => {
  for (
    const invalid of [
      null,
      {},
      { ...body, start: "shell" },
      { ...body, command: "anything" },
      { ...body, start: "mse_report" },
      { ...body, settings: { ...body.settings, mse: "true" } },
      { ...body, settings: { ...body.settings, seed: 3 } },
      { ...body, settings: { ...body.settings, mortality_2: -1 } },
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
