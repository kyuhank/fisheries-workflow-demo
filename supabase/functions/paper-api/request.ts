/** Accept only the supplied demonstration; older downloads omit MSE settings. */
export function runSettings(body: any, jobs: string[]) {
  const settings = body?.settings;
  const keys = settings && Object.keys(settings).sort().join(",");
  if (
    !jobs.includes(body?.start) ||
    !["connected", "manual"].includes(body?.handover) ||
    Object.keys(body || {}).sort().join(",") !== "handover,settings,start" ||
    ![
      "last_year,min_hooks_a,mortality_2",
      "last_year,min_hooks_a,mortality_2,mse",
      "last_year,min_hooks_a,mortality_2,mse,mse_buffer",
    ].includes(keys) ||
    ![2021, 2022, 2023, 2024].includes(settings.last_year) ||
    ![0, 1200].includes(settings.min_hooks_a) ||
    ![.25, .30, .35].includes(settings.mortality_2) ||
    ("mse" in settings && typeof settings.mse !== "boolean") ||
    ("mse_buffer" in settings &&
      (typeof settings.mse_buffer !== "number" ||
        ![.6, .8, 1].includes(settings.mse_buffer))) ||
    (body.start.startsWith("mse_") && settings.mse !== true)
  ) throw Error("Select the supplied demonstration settings.");
  // Preserve missing fields for already downloaded versions.
  return { ...settings };
}
