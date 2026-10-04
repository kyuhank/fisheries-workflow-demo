/** Follow the recorded inputs, including the original run of each reused result. */
function traceInputs(key, records) {
  const chain = {}, visiting = new Set();
  function visit(job) {
    if (visiting.has(job)) throw Error("The input record contains a cycle.");
    if (chain[job]) return;
    const record = records[job];
    if (!record) throw Error("An earlier input is no longer available: " + job);
    visiting.add(job);
    for (const [parent, input] of Object.entries(record.inputs || {})) {
      const saved = records[parent];
      if (
        !saved || saved.run_id !== input.run_id ||
        saved.outputs["output.json"] !== input.checksum
      ) {
        throw Error(
          "The recorded version of " + parent +
            " is no longer in this session. Use its downloaded run.",
        );
      }
      visit(parent);
    }
    visiting.delete(job);
    chain[job] = record;
  }
  visit(key);
  return chain;
}

function recordedSettings(chain, fallback) {
  const values = { ...fallback };
  if (chain.submission) values.last_year = chain.submission.settings.last_year;
  if (chain.cpue_a) values.min_hooks_a = chain.cpue_a.settings.min_hooks;
  const growth = [chain.assessment_a2, chain.assessment_b2]
    .filter(Boolean).map((record) => record.settings.r);
  if (new Set(growth).size > 1) {
    throw Error(
      "These inputs used different growth rate settings. Use the individual downloaded runs.",
    );
  }
  if (growth.length) values.growth_rate_2 = growth[0];
  if (chain.mse_buffered) values.mse_buffer = chain.mse_buffered.settings.buffer ?? 0.8;
  return values;
}

const comparisonAssessmentJobs = ["assessment_a1", "assessment_a2", "assessment_b1", "assessment_b2"];
const comparisonCaseJobs = Object.fromEntries(comparisonAssessmentJobs.map((job) =>
  ["Assessment " + job.split("_")[1].toUpperCase(), job]));
const comparisonGradientFields = ["objective_gradient_logK", "projected_gradient_logK"];

function comparisonFitMatches(expected, actual) {
  return [expected, actual].every((value) => value &&
    typeof value.convergence === "number" && Number.isInteger(value.convergence) &&
    value.convergence === 0 && value.gradient_check === "Pass" &&
    value.gradient_tolerance === 1e-4) &&
    ["none", "lower", "upper"].includes(expected.active_bound) &&
    expected.active_bound === actual.active_bound &&
    expected.fit_method === "RTMB::MakeADFun + nlminb" &&
    expected.fit_method === actual.fit_method;
}

function comparisonNearZero(left, right, pair) {
  return comparisonFitMatches(...pair) && typeof left === "number" &&
    typeof right === "number" && Number.isFinite(left) && Number.isFinite(right) &&
    Math.abs(left) <= 1e-7 && Math.abs(right) <= 1e-7 && Math.abs(left - right) <= 1e-7;
}

function comparisonResidualInvariant(row) {
  return [row.observed_index, row.fitted_index, row.log_residual].every((value) =>
    typeof value === "number" && Number.isFinite(value)) &&
    row.observed_index > 0 && row.fitted_index > 0 &&
    Math.abs(row.log_residual - Math.log(row.observed_index / row.fitted_index)) <= 1e-12;
}

function comparisonResiduals(output, path) {
  if (output.series !== undefined && !Array.isArray(output.series)) return path + ".series";
  for (const [index, row] of (output.series || []).entries()) {
    if (!row || typeof row !== "object") return `${path}.series.${index}`;
    if (Object.hasOwn(row, "log_residual") && !comparisonResidualInvariant(row)) {
      return `${path}.series.${index}.log_residual`;
    }
  }
  return null;
}

function comparisonExact(expected, actual) {
  if (typeof expected === "number") {
    return Number.isFinite(expected) && Number.isFinite(actual) && expected === actual;
  }
  if (expected === null || typeof expected !== "object") return expected === actual;
  return actual && typeof actual === "object" &&
    Array.isArray(expected) === Array.isArray(actual) &&
    Object.keys(expected).sort().join("\n") === Object.keys(actual).sort().join("\n") &&
    Object.keys(expected).every((key) => comparisonExact(expected[key], actual[key]));
}

function comparisonCopies(expected, actual, context, path) {
  if (!context || Object.keys(context).sort().join("\n") !== comparisonAssessmentJobs.slice().sort().join("\n")) {
    return path + ".assessment_context";
  }
  for (const [side, output] of [expected, actual].entries()) {
    const rows = output?.diagnostics;
    if (!Array.isArray(rows) || rows.some((row) => !row || typeof row !== "object")) return path + ".diagnostics";
    const cases = rows.map((row) => row.case);
    if (rows.length !== 4 || new Set(cases).size !== 4 ||
        cases.some((label) => !Object.hasOwn(comparisonCaseJobs, label))) return path + ".diagnostics";
    if (Object.keys(output.series || {}).sort().join("\n") !== Object.keys(comparisonCaseJobs).sort().join("\n")) {
      return path + ".series";
    }
    for (const [index, row] of rows.entries()) {
      const job = comparisonCaseJobs[row.case], pair = context[job], direct = pair?.[side];
      if (!Array.isArray(pair) || pair.length !== 2 || !direct ||
          ![...comparisonGradientFields, "convergence", "gradient_check", "active_bound", "fit_method"]
            .every((field) => Object.hasOwn(row, field))) return `${path}.diagnostics.${index}`;
      for (const [field, value] of Object.entries(row)) {
        if (field !== "case" && (!Object.hasOwn(direct, field) || !comparisonExact(value, direct[field]))) {
          return `${path}.diagnostics.${index}.${field}`;
        }
      }
      if (!comparisonExact(output.series[row.case], direct.series)) return `${path}.series.${row.case}`;
      const invalid = comparisonResiduals(direct, job);
      if (invalid) return invalid;
    }
  }
  return null;
}

function compareOutput(expected, actual, path = "output", assessmentContext = null) {
  const gradients = new Map(), residualRows = new Map();
  function registerSeries(seriesPath, left, right, pair) {
    if (Array.isArray(left) && Array.isArray(right)) {
      left.forEach((_, index) => residualRows.set(seriesPath + "." + index, pair));
    }
  }
  if (comparisonAssessmentJobs.includes(path) && expected && actual &&
      typeof expected === "object" && typeof actual === "object") {
    const invalid = comparisonResiduals(expected, path) || comparisonResiduals(actual, path);
    if (invalid) return invalid;
    const pair = [expected, actual];
    gradients.set(path, pair);
    registerSeries(path + ".series", expected.series, actual.series, pair);
  }
  if (["assessment_summary", "assessment_report"].includes(path) && assessmentContext !== null) {
    const invalid = comparisonCopies(expected, actual, assessmentContext, path);
    if (invalid) return invalid;
    expected.diagnostics.forEach((row, index) => {
      const pair = assessmentContext[comparisonCaseJobs[row.case]];
      if (row.case === actual.diagnostics[index].case) gradients.set(path + ".diagnostics." + index, pair);
      registerSeries(path + ".series." + row.case, expected.series[row.case], actual.series[row.case], pair);
    });
  }
  return compareValue(expected, actual, path);

  function compareValue(expected, actual, current) {
  if (typeof expected === "number") {
    return Number.isFinite(expected) && typeof actual === "number" && Number.isFinite(actual) &&
        Math.abs(expected - actual) <=
          Math.max(1e-9, 1e-6 * Math.max(Math.abs(expected), Math.abs(actual)))
      ? null
      : current;
  }
  if (expected === null || typeof expected !== "object") {
    return expected === actual ? null : current;
  }
  if (
    !actual || typeof actual !== "object" ||
    Array.isArray(expected) !== Array.isArray(actual) ||
    Object.keys(expected).sort().join("\n") !==
      Object.keys(actual).sort().join("\n")
  ) return current;
  for (const key of Object.keys(expected)) {
    const pair = gradients.get(current);
    if (pair && comparisonGradientFields.includes(key) && comparisonNearZero(expected[key], actual[key], pair)) continue;
    const residualPair = residualRows.get(current);
    if (residualPair && key === "log_residual" && comparisonFitMatches(...residualPair) &&
        typeof expected[key] === "number" && typeof actual[key] === "number" &&
        Number.isFinite(expected[key]) && Number.isFinite(actual[key]) &&
        Math.abs(expected[key] - actual[key]) <=
          Math.max(1e-8, 1e-6 * Math.max(Math.abs(expected[key]), Math.abs(actual[key])))) continue;
    const difference = compareValue(
      expected[key],
      actual[key],
      current + "." + key,
    );
    if (difference) return difference;
  }
  return null;
  }
}

function compareMaterials(reference, current) {
  const changed = new Set();
  for (const [key, record] of Object.entries(reference)) {
    const next = current[key];
    if (!next) {
      changed.add("missing jobs");
      continue;
    }
    for (
      const [field, label] of [["code", "code"], ["data_files", "data files"], [
        "settings",
        "settings",
      ]]
    ) {
      if (compareOutput(record[field], next[field])) changed.add(label);
    }
    if (
      compareOutput(record.software, next.software) ||
      record.execution?.container !== next.execution?.container
    ) changed.add("software");
    if (record.execution?.data_checksum !== next.execution?.data_checksum) {
      changed.add("hosted data");
    }
  }
  return [...changed];
}
