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
  const mortality = [chain.assessment_a2, chain.assessment_b2]
    .filter(Boolean).map((record) => record.settings.M);
  if (new Set(mortality).size > 1) {
    throw Error(
      "These inputs used different mortality settings. Use the individual downloaded runs.",
    );
  }
  if (mortality.length) values.mortality_2 = mortality[0];
  return values;
}

function compareOutput(expected, actual, path = "output") {
  if (typeof expected === "number") {
    return typeof actual === "number" && Number.isFinite(actual) &&
        Math.abs(expected - actual) <=
          Math.max(1e-9, 1e-6 * Math.max(Math.abs(expected), Math.abs(actual)))
      ? null
      : path;
  }
  if (expected === null || typeof expected !== "object") {
    return expected === actual ? null : path;
  }
  if (
    !actual || typeof actual !== "object" ||
    Array.isArray(expected) !== Array.isArray(actual) ||
    Object.keys(expected).sort().join("\n") !==
      Object.keys(actual).sort().join("\n")
  ) return path;
  for (const key of Object.keys(expected)) {
    const difference = compareOutput(
      expected[key],
      actual[key],
      path + "." + key,
    );
    if (difference) return difference;
  }
  return null;
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
