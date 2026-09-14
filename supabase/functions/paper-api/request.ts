/** Accept only the supplied demonstration; older downloads omit the MSE flag. */
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
    ].includes(keys) ||
    ![2021, 2022, 2023, 2024].includes(settings.last_year) ||
    ![0, 1200].includes(settings.min_hooks_a) ||
    ![.25, .30, .35].includes(settings.mortality_2) ||
    ("mse" in settings && typeof settings.mse !== "boolean") ||
    (body.start.startsWith("mse_") && settings.mse !== true)
  ) throw Error("Select the supplied demonstration settings.");
  // Preserve the original three-field request for already downloaded versions.
  return { ...settings };
}
