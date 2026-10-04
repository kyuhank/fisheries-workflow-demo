# Small closed-loop trials around the fitted Schaefer cases.
# Common recorded growth/observation errors let the three rules face the same trials.

MSE_CASES <- c("assessment_a1", "assessment_a2", "assessment_b1", "assessment_b2")
MSE_RULES <- list(
  constant = list(name = "Constant catch", description = "Keep catch at its recent mean."),
  index = list(name = "Index rule", description = "Scale catch by the three-year mean observed index."),
  buffered = list(name = "Buffered rule", description = "Apply an index step, catch buffer and annual advice limit."))
MSE_ASSUMPTIONS <- list(
  seed = 20260915L, years = 15L, replicates = 20L,
  growth_cv = 0.20, observation_cv = 0.15, index_window = 3L,
  maximum_catch_multiple = 2, annual_change_limit = 0.15,
  maximum_harvest_rate = 0.4, maximum_growth_rate = 1,
  depletion_threshold = 0.2,
  buffered_steps = list(thresholds = json_array(c(0.8, 1.1)), multipliers = json_array(c(0.5, 1, 1.25))),
  rng = list(uniform = "Mersenne-Twister", normal = "Inversion", sample = "Rejection"),
  example_trial = list(case = "assessment_a1", scenario = "lower", replicate = 1L),
  scenarios = list(
    list(key = "baseline", name = "Baseline growth", growth_multipliers = json_array(rep(1, 15))),
    list(key = "lower", name = "Growth dip and recovery",
         growth_multipliers = json_array(c(rep(0.7, 6), rep(1, 9))))))

mse_prepare <- function(assessments) {
  require_condition(setequal(names(assessments), MSE_CASES),
                    "MSE preparation requires all four assessment cases.")
  models <- lapply(MSE_CASES, function(key) {
    fit <- assessments[[key]]
    rows <- fit$series
    require_condition(length(rows) >= 3 && all(diff(rows_values(rows, "year")) == 1),
                      "MSE preparation requires consecutive annual assessment rows.")
    require_condition(all(is.finite(c(fit$K, fit$r, fit$q)) & c(fit$K, fit$r, fit$q) > 0),
                      "Operating-model capacity, growth and catchability must be positive and finite.")
    catches <- rows_values(rows, "catch_t")
    path <- surplus_path(fit$K, fit$r, catches)
    # The last assessment catch is applied once by this path; start at its final state.
    B <- tail(path, 1)
    require_condition(is.finite(B) && B > 0 && B <= fit$K * (1 + 1e-8),
                      "The assessment has no feasible next-year stock state.")
    require_condition(abs(B - fit$next_biomass_t) <= 1e-8 * max(1, B),
                      "The assessment and reconstructed next-year stock do not agree.")
    recent <- tail(rows_values(rows, "observed_index"), 3)
    require_condition(all(is.finite(recent) & recent > 0),
                      "Reference CPUE indices must be positive and finite.")
    list(case = key, name = paste("Assessment", toupper(sub("assessment_", "", key))),
         first_year = tail(rows_values(rows, "year"), 1) + 1,
         B = unname(B), K = fit$K, r = fit$r, q = fit$q,
         reference_catch_t = mean(tail(catches, 3)), reference_index = mean(recent),
         recent_indices = json_array(recent), boundary_fit = fit$boundary_fit)
  })
  require_condition(length(unique(rows_values(models, "first_year"))) == 1,
                    "MSE cases must end in the same assessment year.")
  assumptions <- MSE_ASSUMPTIONS
  RNGkind(assumptions$rng$uniform, assumptions$rng$normal, assumptions$rng$sample)
  growth_sigma <- sqrt(log1p(assumptions$growth_cv^2))
  observation_sigma <- sqrt(log1p(assumptions$observation_cv^2))
  streams <- list()
  for (case in seq_along(models)) {
    for (scenario in seq_along(assumptions$scenarios)) {
      for (replicate in seq_len(assumptions$replicates)) {
        seed <- assumptions$seed + (case - 1L) * 10000L +
          (scenario - 1L) * 1000L + replicate - 1L
        set.seed(seed)
        z <- matrix(stats::rnorm(2L * assumptions$years), ncol = 2L, byrow = TRUE)
        errors <- lapply(seq_len(assumptions$years), function(year) {
          list(growth = exp(growth_sigma * z[year, 1] - growth_sigma^2 / 2),
               observation = exp(observation_sigma * z[year, 2] - observation_sigma^2 / 2))
        })
        streams[[length(streams) + 1L]] <- list(
          case = models[[case]]$case, scenario = assumptions$scenarios[[scenario]]$key,
          replicate = replicate, seed = seed,
          random_stream = paste("R/Mersenne-Twister/Inversion", seed, sep = ":"),
          errors = errors)
      }
    }
  }
  list(operating_models = models, assumptions = assumptions, rules = MSE_RULES,
       error_streams = streams,
       objectives = json_array(c("Compare catches", "Avoid low biomass", "Limit catch changes")),
       scope = "Illustrative seeded closed-loop Schaefer trials; no management advice.",
       limitations = json_array(c(
         "Fixed growth sensitivities and initial biomass; fitted cases are not weighted probabilities.",
         "Growth and observation errors are declared toy lognormal perturbations.",
         "No assessment is refitted during these management trials.",
         "Empirical trial fractions are conditional illustrations, not validated risk estimates.",
         "Annual growth is capped at one to retain the simple Euler update within its stable range.")))
}

catch_decision <- function(rule, recent, reference_index, reference_catch, previous, assumptions) {
  ratio <- mean(tail(recent, assumptions$index_window)) / reference_index
  target <- reference_catch * min(assumptions$maximum_catch_multiple, max(0, ratio))
  band <- "proportional"
  if (rule == "constant") {
    target <- reference_catch
    band <- "constant"
  }
  if (rule == "buffered") {
    steps <- assumptions$buffered_steps
    position <- sum(ratio >= numeric_values(steps$thresholds)) + 1L
    target <- reference_catch * numeric_values(steps$multipliers)[position] * assumptions$buffer
    band <- c("low", "middle", "high")[position]
    change <- assumptions$annual_change_limit
    requested <- min(previous * (1 + change), max(previous * (1 - change), target))
  } else {
    requested <- target
  }
  list(index_ratio = ratio, target_catch_t = target,
       requested_catch_t = requested, decision_band = band)
}

mse_trial <- function(model, rule, scenario, assumptions, errors) {
  B <- model$B
  recent <- numeric_values(model$recent_indices)
  previous <- model$reference_catch_t
  profile <- numeric_values(scenario$growth_multipliers)
  require_condition(length(errors) == assumptions$years && length(profile) == assumptions$years,
                    "Each MSE trial needs a growth scenario and paired errors for every year.")
  rows <- vector("list", assumptions$years)
  for (year in seq_len(assumptions$years)) {
    observed <- model$q * B * errors[[year]]$observation
    recent <- c(recent, observed)
    decision <- catch_decision(rule, recent, model$reference_index,
                               model$reference_catch_t, previous, assumptions)
    requested <- decision$requested_catch_t
    realised <- min(requested, assumptions$maximum_harvest_rate * B)
    growth <- min(assumptions$maximum_growth_rate,
                  model$r * profile[year] * errors[[year]]$growth)
    following <- B + growth * B * (1 - B / model$K) - realised
    rows[[year]] <- c(list(year = model$first_year + year - 1L, observed_index = observed), decision,
             list(catch_t = realised, harvest_rate = realised / B, biomass_t = B,
                  start_B_over_K = B / model$K, B_over_K = following / model$K,
                  growth_multiplier = profile[year], growth_rate = growth,
                  catch_shortfall_t = requested - realised))
    B <- following
    previous <- requested
  }
  catches <- c(model$reference_catch_t, rows_values(rows, "catch_t"))
  list(rows = rows, mean_catch_t = mean(catches[-1]),
       final_B_over_K = tail(rows_values(rows, "B_over_K"), 1),
       below_threshold = any(pmin(rows_values(rows, "start_B_over_K"),
                                  rows_values(rows, "B_over_K")) < assumptions$depletion_threshold),
       catch_change_percent = 100 * sum(abs(diff(catches))) / max(sum(catches[-1]), 1e-12),
       shortfall_years = sum(rows_values(rows, "catch_shortfall_t") > 1e-8))
}

mse_metrics <- function(trials) {
  list(trials = length(trials), mean_catch_t = mean(rows_values(trials, "mean_catch_t")),
       final_B_over_K = stats::median(rows_values(trials, "final_B_over_K")),
       below_threshold_percent = 100 * mean(rows_values(trials, "below_threshold")),
       catch_change_percent = mean(rows_values(trials, "catch_change_percent")),
       shortfall_trials = sum(rows_values(trials, "shortfall_years") > 0))
}

mse_annual <- function(paths) {
  fields <- c("catch_t", "B_over_K", "start_B_over_K", "index_ratio",
              "target_catch_t", "requested_catch_t", "growth_multiplier")
  lapply(seq_along(paths[[1]]), function(year) {
    rows <- lapply(paths, function(path) path[[year]])
    values <- setNames(lapply(fields, function(field) stats::median(rows_values(rows, field))), fields)
    c(list(year = rows[[1]]$year), values)
  })
}

mse_simulate <- function(prepared, rule, buffer = NULL) {
  require_condition(rule %in% names(MSE_RULES), "Unknown MSE management rule.")
  require_condition(is.null(buffer) || (rule == "buffered" && buffer %in% c(0.6, 0.8, 1)),
                    "Select one of the supplied Buffered rule catch fractions.")
  assumptions <- prepared$assumptions
  rule_settings <- if (rule == "buffered") list(buffer = optional_value(buffer, 0.8)) else empty_object()
  effective <- assumptions
  if (rule == "buffered") effective$buffer <- rule_settings$buffer
  trials <- list()
  paths <- list()
  example <- NULL
  for (stream in prepared$error_streams) {
    model <- prepared$operating_models[[match(stream$case, rows_values(prepared$operating_models, "case"))]]
    scenario <- assumptions$scenarios[[match(stream$scenario, rows_values(assumptions$scenarios, "key"))]]
    trial <- mse_trial(model, rule, scenario, effective, stream$errors)
    paths[[length(paths) + 1L]] <- trial$rows
    trials[[length(trials) + 1L]] <- c(trial[names(trial) != "rows"],
      stream[c("case", "scenario", "replicate", "seed", "random_stream")])
    selected <- assumptions$example_trial
    if (stream$case == selected$case && stream$scenario == selected$scenario &&
        stream$replicate == selected$replicate) {
      example <- list(case = model$name, scenario = scenario$name, case_key = stream$case,
                      scenario_key = stream$scenario, replicate = stream$replicate,
                      seed = stream$seed, rows = trial$rows,
                      reference_catch_t = model$reference_catch_t,
                      reference_index = model$reference_index,
                      selection = "Specified before simulation; the same trial is shown for every rule.")
    }
  }
  require_condition(length(trials) > 0 && !is.null(example), "The selected MSE trials are missing.")
  scenarios <- lapply(assumptions$scenarios, function(scenario) {
    selected <- which(rows_values(trials, "scenario") == scenario$key)
    list(key = scenario$key, name = scenario$name, series = mse_annual(paths[selected]),
         metrics = mse_metrics(trials[selected]))
  })
  cases <- list()
  for (model in prepared$operating_models) {
    for (scenario in assumptions$scenarios) {
      selected <- Filter(function(row) row$case == model$case && row$scenario == scenario$key, trials)
      cases[[length(cases) + 1L]] <- c(list(case = model$name, scenario = scenario$name), mse_metrics(selected))
    }
  }
  annual <- lapply(mse_annual(paths), function(row) row[c("year", "catch_t", "B_over_K")])
  description <- MSE_RULES[[rule]]$description
  if (rule == "buffered") description <- sprintf(
    "Apply an index step and %.0f%% catch buffer; limit annual advice changes to %.0f%%.",
    100 * rule_settings$buffer, 100 * assumptions$annual_change_limit)
  list(rule = rule, name = MSE_RULES[[rule]]$name, description = description,
       rule_settings = rule_settings, assumptions = assumptions,
       metrics = mse_metrics(trials), series = annual, scenarios = scenarios, cases = cases,
       trials = trials, example = example, operating_models = prepared$operating_models,
       error_streams = prepared$error_streams, limitations = prepared$limitations,
       scope = prepared$scope,
       boundary_cases = json_array(rows_values(Filter(function(model) model$boundary_fit,
                                                prepared$operating_models), "name")))
}

mse_summarise <- function(results) {
  by_rule <- setNames(results, rows_values(results, "rule"))
  require_condition(length(results) == 3 && setequal(names(by_rule), names(MSE_RULES)),
                    "MSE comparison requires each of the three management rules.")
  first <- by_rule$constant
  for (result in by_rule) {
    require_condition(identical(result$assumptions, first$assumptions) &&
                        identical(result$operating_models, first$operating_models) &&
                        identical(result$error_streams, first$error_streams),
                      "MSE rules must use the same operating models, scenarios and actual error streams.")
  }
  rule_names <- vapply(by_rule, function(result) result$name, character(1))
  metrics <- lapply(names(MSE_RULES), function(rule) {
    c(list(rule = rule, name = by_rule[[rule]]$name), by_rule[[rule]]$metrics)
  })
  cases <- unname(do.call(c, lapply(by_rule, function(result) {
    lapply(result$cases, function(row) c(list(rule = result$name), row))
  })))
  scenarios <- lapply(seq_along(first$scenarios), function(i) {
    list(key = first$scenarios[[i]]$key, name = first$scenarios[[i]]$name,
         series = setNames(lapply(by_rule, function(result) result$scenarios[[i]]$series), rule_names),
         metrics = lapply(names(MSE_RULES), function(rule) {
           c(list(rule = rule, name = by_rule[[rule]]$name), by_rule[[rule]]$scenarios[[i]]$metrics)
         }))
  })
  list(series = setNames(lapply(by_rule, function(result) result$series), rule_names), metrics = metrics,
       cases = cases, assumptions = first$assumptions,
       rules = lapply(by_rule, function(result) {
         list(name = result$name, description = result$description, settings = result$rule_settings)
       }), operating_models = first$operating_models, error_streams = first$error_streams,
       limitations = first$limitations, boundary_cases = first$boundary_cases, scope = first$scope,
       scenarios = scenarios, examples = setNames(lapply(by_rule, function(result) result$example), rule_names))
}
