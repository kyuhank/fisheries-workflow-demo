# Separate MQMF adoption helpers. GPL-3; see LICENSE and THIRD_PARTY.md.
# The full external/MQMF/R/spm.r file is preserved and sourced unchanged.

study_load <- function(path) {
  environment <- new.env(parent = baseenv())
  loaded <- load(path, envir = environment)
  require_condition(identical(loaded, "abdat"), "Expected original abdat object")
  environment$abdat
}

study_check_data <- function(data) {
  require_condition(is.data.frame(data) || is.matrix(data), "Expected table/matrix")
  require_condition(identical(colnames(data), c("year", "catch", "cpue")) &&
                      nrow(data) == 24L && ncol(data) == 3L, "Expected 24 by 3 abdat")
  values <- as.matrix(data)
  require_condition(is.numeric(values) && all(is.finite(values)), "Non-finite input")
  require_condition(identical(as.numeric(values[, "year"]), as.numeric(1985:2008)),
                    "Require consecutive sorted annual years 1985 to 2008")
  require_condition(all(values[, "catch"] >= 0) && all(values[, "cpue"] > 0),
                    "Require non-negative tonnes and positive source-scale CPUE")
  invisible(values)
}

study_mapped <- function(path) {
  rows <- jsonlite::fromJSON(path, simplifyVector = FALSE)$rows
  require_condition(length(rows) == 24L, "Mapped JSON must have 24 rows")
  check_row_fields(rows, c("year", "catch", "cpue"))
  require_condition(all(vapply(rows, function(row) identical(sort(names(row)),
                    sort(c("year", "catch", "cpue"))), logical(1))), "Unexpected fields")
  values <- do.call(rbind, lapply(rows, function(row)
    vapply(c("year", "catch", "cpue"), function(name) as.numeric(row[[name]]), numeric(1))))
  colnames(values) <- c("year", "catch", "cpue")
  study_check_data(values)
  values
}

study_prediction <- function(context, direct) {
  original <- study_load(context$study$raw_path)
  native <- study_check_data(original)
  indat <- original
  mapping <- NULL
  if (!direct) {
    csv <- utils::read.csv(context$study$csv_path, check.names = FALSE,
                           colClasses = c("numeric", "numeric", "numeric"))
    mapped <- study_mapped(context$study$json_path)
    require_condition(identical(unname(native), unname(as.matrix(csv))) &&
                        identical(unname(native), unname(mapped)),
                      "All 72 numeric values must round-trip exactly")
    indat <- mapped
    mapping <- list(numeric_values = 72L, exact = TRUE, route = "RData -> CSV -> JSON -> matrix")
  }
  parameters <- jsonlite::fromJSON(context$study$parameter_path, simplifyVector = FALSE)
  require_condition(identical(sort(names(parameters)), sort(c("r", "K", "Binit", "sigma", "schaefer"))) &&
                      parameters$r %in% c(0.4, 0.35) && parameters$K == 9400 &&
                      parameters$Binit == 3400 && parameters$sigma == 0.05 &&
                      isTRUE(parameters$schaefer), "Unexpected frozen parameter values")
  require_condition(all(vapply(names(parameters), function(name)
    identical(parameters[[name]], context$job_settings[[name]]), logical(1))),
    "Parameter bytes/context differ")
  upstream <- new.env(parent = baseenv())
  source(context$study$function_path, local = upstream, echo = FALSE)
  require_condition(is.function(upstream$simpspm), "Unchanged simpspm unavailable")
  param <- log(c(r = parameters$r, K = parameters$K,
                 Binit = parameters$Binit, sigma = parameters$sigma))
  # One call only: identical upstream implementation in direct and adapter routes.
  prediction <- upstream$simpspm(pars = param, indat = indat, schaefer = TRUE)
  require_condition(length(prediction) == 24L && all(is.finite(prediction)),
                    "Require 24 finite natural-log predictions")
  list(schema_version = 1L, quantity = "predicted_cpue", transformation = "natural_log",
       numerical_scale = "MQMF-abdat-source-scale", physical_unit = "unspecified",
       normalisation = "unspecified; none applied by study",
       observed_contract = list(quantity = "observed_cpue", transformation = "linear",
                                numerical_scale = "MQMF-abdat-source-scale", physical_unit = "unspecified"),
       catch_unit = "tonnes", year_start = 1985L, year_end = 2008L,
       input_route = if (direct) "original RData object" else "lossless CSV -> JSON -> matrix",
       mapping = mapping, parameters = parameters, producer = context$producer,
       semantics = list(population_parameters = "fixed supplied teaching values",
                        q = "estimated internally in closed form from positive CPUE/conditional biomass",
                        sigma = "accepted but unused", biomass_floor = 40,
                        optimisation = FALSE, biological_validation = FALSE),
       series = lapply(seq_along(prediction), function(i)
         list(year = as.numeric(native[i, "year"]), observed_cpue = native[i, "cpue"],
              predicted_log_cpue = prediction[i])))
}

study_consume <- function(context) {
  keys <- c("cpue_b", "cpue_a")
  for (key in keys) {
    value <- context$parents[[key]]
    require_condition(identical(value$quantity, "predicted_cpue") &&
                        identical(value$transformation, "natural_log") &&
                        identical(value$numerical_scale, "MQMF-abdat-source-scale") &&
                        identical(value$physical_unit, "unspecified") &&
                        identical(value$normalisation, "unspecified; none applied by study"),
                      "Prediction contract requires natural log in the documented source scale")
    require_condition(identical(value$observed_contract$quantity, "observed_cpue") &&
                        identical(value$observed_contract$transformation, "linear") &&
                        identical(value$observed_contract$numerical_scale, "MQMF-abdat-source-scale") &&
                        identical(value$observed_contract$physical_unit, "unspecified"),
                      "Observed CPUE requires its linear source-scale contract")
    require_condition(identical(value$producer, context$input_producers[[key]]),
                      "Actual producer identity mismatch")
    require_condition(identical(as.numeric(rows_values(value$series, "year")), as.numeric(1985:2008)),
                      "Require equal consecutive annual years")
    require_condition(all(is.finite(rows_values(value$series, "predicted_log_cpue"))),
                      "Non-finite prediction")
    observed <- rows_values(value$series, "observed_cpue")
    require_condition(length(observed) == 24L && all(is.finite(observed) & observed > 0),
                      "Require 24 finite positive observed CPUE values")
  }
  observed <- rows_values(context$parents$cpue_b$series, "observed_cpue")
  require_condition(identical(observed, rows_values(context$parents$cpue_a$series, "observed_cpue")),
                    "Producer observations must agree exactly in source scale")
  reference <- rows_values(context$parents$cpue_b$series, "predicted_log_cpue")
  active <- rows_values(context$parents$cpue_a$series, "predicted_log_cpue")
  tolerance <- context$study$tolerance
  require_condition(tolerance$absolute == 1e-12 && tolerance$relative == 1e-12,
                    "Frozen tolerance changed")
  close <- abs(active - reference) <= pmax(tolerance$absolute,
                         tolerance$relative * pmax(abs(active), abs(reference)))
  baseline <- context$parents$cpue_a$parameters$r == 0.4
  if (baseline) require_condition(all(close), "Native/adapter preservation failed")
  if (!baseline) require_condition(any(!close), "Declared growth perturbation has no detectable effect")
  ratio <- exp(active - reference)
  require_condition(all(is.finite(ratio) & ratio > 0), "Non-finite source-scale ratio")
  list(schema_version = 1L, description = "Conditional MQMF teaching prediction comparison",
       quantity = "predicted_cpue", transformation = "natural_log",
       numerical_scale = "MQMF-abdat-source-scale", physical_unit = "unspecified",
       observed_contract = context$parents$cpue_b$observed_contract,
       producers = context$input_producers, input_links = context$input_links,
       tolerance = tolerance, baseline_preservation = if (baseline) all(close) else NULL,
       perturbation_detectable = if (!baseline) any(!close) else NULL,
       rows = lapply(seq_along(active), function(i) list(year = 1984L + i, observed_cpue = observed[i],
         reference_predicted_log_cpue = reference[i], active_predicted_log_cpue = active[i],
         log_difference = active[i] - reference[i], source_scale_ratio = ratio[i])),
       limit = "No optimisation, biological validation or management advice; CPUE standardisation is not reproduced")
}
