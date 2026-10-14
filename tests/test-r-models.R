# Meaningful scientific sanity checks. Execute only in the authorised R container.
driver <- new.env(parent = globalenv())
source("workflow/r_driver.R", local = driver)
driver$workflow_require_container()
source("workflow/r/common.R")
source("workflow/r/models.R")
source("workflow/r/mse.R")
stopifnot(requireNamespace("RTMB", quietly = TRUE))

close <- function(actual, expected, tolerance = 1e-7) {
  stopifnot(all(is.finite(actual)),
            max(abs(actual - expected) / pmax(1, abs(expected))) < tolerance)
}
rejects <- function(expression) {
  stopifnot(inherits(tryCatch({ force(expression); NULL }, error = identity), "error"))
}

# Known Poisson score totals: changing effort by year must not enter the index.
# Zero-count observations are retained; both vessel and year coefficients are known.
sets <- list()
for (year in 1:3) {
  for (vessel in c("A", "B")) {
    rate <- 10 * c(1, 1.5, 2)[year] * if (vessel == "A") 1 else 2
    for (observation in 1:2) {
      hooks <- 1000 * year * observation
      count <- if (observation == 1) 0 else rate * 3 * year
      sets[[length(sets) + 1L]] <- list(set_id = paste(year, vessel, observation),
        year = 2000 + year, vessel = vessel, hooks = hooks, catch_n = count)
    }
  }
}
a <- cpue(sets, TRUE)
b <- cpue(sets, FALSE)
close(rows_values(a$series, "index"), c(1, 1.5, 2))
close(rows_values(b$series, "index"), c(1, 1.5, 2))
stopifnot(a$sets_used == 12, a$converged, a$score_residual < 1e-7,
          cpue(sets, TRUE, 1200)$sets_excluded == 2)
invalid <- sets
invalid[[1]]$hooks <- 0
rejects(cpue(invalid))
missing <- sets
for (i in seq(1, length(missing), by = 2)) missing[[i]]$catch_n <- NULL
rejects(cpue(missing))
invalid <- sets
invalid[[1]]$catch_n <- list(0, 1)
rejects(cpue(invalid))

# Public aggregate fixture: changing spatial effort composition changes nominal
# CPUE, while the known equal-stratum standardised trend is preserved.
# These are synthetic test rows, not released WCPFC observations.
aggregates <- list()
for (year in 1:3) {
  for (stratum in c("20S_175E_Q1", "20S_175E_Q2")) {
    first <- stratum == "20S_175E_Q1"
    hooks <- 1000 * (if (first) 4 - year else year)
    rate <- 10 * c(1, 1.5, 2)[year] * if (first) 1 else 2
    for (observation in 1:2) {
      aggregates[[length(aggregates) + 1L]] <- list(
        set_id = paste(year, stratum, observation), year = 2000 + year,
        fleet = "TEST", cell = "20S_175E", quarter = if (first) 1 else 2,
        stratum = stratum, hooks = hooks,
        catch_n = if (observation == 1) 0 else 2 * rate * hooks / 1000)
    }
  }
}
public_a <- cpue(aggregates, stratum_effect = TRUE)
public_b <- cpue(aggregates, stratum_effect = FALSE)
close(rows_values(public_a$series, "index"), c(1, 1.5, 2))
close(rows_values(public_a$series, "standardised_cpue"), c(15, 22.5, 30))
close(rows_values(public_a$series, "nominal_cpue"), c(12.5, 22.5, 35))
close(rows_values(public_b$series, "standardised_cpue"), c(15, 22.5, 30))
close(rows_values(public_b$series, "index"), c(1, 1.5, 2))
stopifnot(public_b$method == "Quasipoisson GLM: year + quarter",
          public_b$quarter_score_residual < 1e-7,
          public_b$score_residual == max(public_b$year_score_residual,
                                         public_b$quarter_score_residual),
          all(rows_values(public_b$prediction_grid, "quarter") %in% 1:2))
stopifnot(public_a$sets_used == 12, public_a$released_zero_rows == 6,
          public_a$data_kind == "public-wcpfc", public_a$converged,
          public_a$rank == public_a$model_columns,
          public_a$year_score_residual < 1e-7, public_a$stratum_score_residual < 1e-7,
          is.finite(public_a$dispersion), public_a$dispersion >= 0,
          public_a$normalisation$reference_year == 2001,
          length(public_a$prediction_grid) == 6, length(public_a$weights) == 2,
          all(rows_values(public_a$weights, "weight") == 0.5),
          all(rows_values(public_a$prediction_grid, "hooks") == 1000),
          is.null(public_a$reference_vessel))
filtered <- cpue(aggregates, min_hooks = 2000)
stopifnot(filtered$rows_excluded == 4, length(filtered$prediction_grid) == 6,
          identical(filtered$weights, public_a$weights))
rejects(cpue(aggregates, min_hooks = 3000))
rejects(cpue(aggregates, min_hooks = -1))
disconnected <- Filter(function(row) {
  (row$year == 2001 && row$quarter == 1) || (row$year == 2002 && row$quarter == 2)
}, aggregates)
rejects(cpue(disconnected))
missing <- aggregates
missing[[1]]$catch_n <- NULL
rejects(cpue(missing))
mixed_fleets <- aggregates
mixed_fleets[[1]]$fleet <- "OTHER"
rejects(cpue(mixed_fleets))
zero_year <- lapply(aggregates, function(row) {
  if (row$year == 2001) row$catch_n <- 0
  row
})
rejects(cpue(zero_year))

# Known seasonal effects on six strata: fixed stratum weights imply quarter
# weights 1/6, 1/6, 1/3, 1/3, rather than four equal quarter weights.
seasonal_rows <- list()
support <- data.frame(cell = c(rep("20S_175E", 4), rep("25S_175E", 2)),
                      quarter = c(1:4, 3:4))
for (year in 1:3) {
  for (i in seq_len(nrow(support))) {
    quarter <- support$quarter[i]
    hooks <- 1000 * if (year == 1) 5 - quarter else if (year == 2) 1 else quarter
    rate <- 10 * c(1, 1.5, 2)[year] * quarter
    for (observation in 1:2) {
      seasonal_rows[[length(seasonal_rows) + 1L]] <- list(
        set_id = paste(year, i, observation), year = 2000 + year,
        fleet = "TEST", cell = support$cell[i], quarter = quarter,
        stratum = paste0(support$cell[i], "_Q", quarter), hooks = hooks,
        catch_n = if (observation == 1) 0 else 2 * rate * hooks / 1000)
    }
  }
}
seasonal_b <- cpue(seasonal_rows, stratum_effect = FALSE)
close(rows_values(seasonal_b$series, "standardised_cpue"), (85 / 3) * c(1, 1.5, 2))
close(rows_values(seasonal_b$series, "index"), c(1, 1.5, 2))
close(rows_values(seasonal_b$quarter_weights, "weight"), c(1/6, 1/6, 1/3, 1/3))
stopifnot(seasonal_b$rank == 6, seasonal_b$residual_degrees_of_freedom == 30,
          seasonal_b$released_zero_rows == 18, length(seasonal_b$prediction_grid) == 18,
          seasonal_b$score_residual == max(seasonal_b$year_score_residual,
                                           seasonal_b$quarter_score_residual))
for (point in seasonal_b$series) {
  selected <- Filter(function(row) row$year == point$year, seasonal_rows)
  close(point$nominal_cpue, 1000 * sum(rows_values(selected, "catch_n")) /
          sum(rows_values(selected, "hooks")))
}
for (point in seasonal_b$prediction_grid) {
  close(point$predicted_cpue, 10 * c(1, 1.5, 2)[point$year - 2000] * point$quarter)
  stopifnot(point$quarter == support$quarter[match(
    point$stratum, paste0(support$cell, "_Q", support$quarter))])
}
for (quarter in list(NULL, NA_real_, 0, 5, 1.5, "1")) {
  invalid_quarter <- seasonal_rows
  invalid_quarter[[1]]$quarter <- quarter
  rejects(cpue(invalid_quarter, stratum_effect = FALSE))
}
rejects(cpue(Filter(function(row) row$quarter == 1, seasonal_rows),
             stratum_effect = FALSE))
rejects(cpue(disconnected, stratum_effect = FALSE))
zero_quarter <- lapply(seasonal_rows, function(row) {
  if (row$quarter == 1) row$catch_n <- 0
  row
})
rejects(cpue(zero_quarter, stratum_effect = FALSE))
aggregate_catches <- lapply(2001:2003, function(year) list(year = year, catch_t = 10))
description <- describe_data(aggregates, aggregate_catches)
stopifnot(description$grouping_field == "stratum", length(description$strata) == 2,
          identical(description$fleets, list("TEST")), is.null(description$vessels),
          any(rows_values(description$fields, "name") == "fleet"),
          !any(rows_values(description$fields, "name") == "vessel"),
          all(rows_values(description$annual, "observations") == 4))
submission_job <- new.env(parent = globalenv())
source("jobs/submission/run.R", local = submission_job)
submitted <- submission_job$calculate(list(
  source = list(sets = aggregates, catch = aggregate_catches), settings = list(last_year = 2003)))
stopifnot(identical(submitted$sets, aggregates))
qc_job <- new.env(parent = globalenv())
source("jobs/qc/run.R", local = qc_job)
quality <- qc_job$calculate(list(parents = list(submission = submitted)))
stopifnot(length(quality$returned) == 0, is.null(attr(quality, "workflow_effects")))
summary_job <- new.env(parent = globalenv())
source("jobs/cpue_summary/run.R", local = summary_job)
comparison <- summary_job$calculate(list(parents = list(cpue_a = public_a, cpue_b = public_b)))
stopifnot(comparison$data_kind == "public-wcpfc", length(comparison$analyses) == 2,
          identical(comparison$analyses[[1]]$weights, public_a$weights))

# Hosted all-years rows are complete and must not append a NULL submission batch.
hosted_row <- sets[[1]]
hosted_row$year <- 2024
hosted <- source_rows(list(sets = list(hosted_row),
                           catch = list(list(year = 2024, catch_t = 10)), submission = NULL), 2024)
stopifnot(length(hosted$sets) == 1, length(hosted$catch) == 1, hosted$catch[[1]]$catch_t == 10)

# A known, noiseless stock path gives an identifiable one-parameter fit.
K <- 5000
r <- 0.30
catches <- seq(200, 500, length.out = 16)
biomass <- numeric(length(catches) + 1L)
biomass[1] <- K
for (i in seq_along(catches)) {
  biomass[i + 1L] <- biomass[i] + r * biomass[i] * (1 - biomass[i] / K) - catches[i]
}
index <- biomass[-length(biomass)] / K
inputs <- lapply(seq_along(catches), function(i) {
  list(year = 2000 + i, index = index[i], catch_t = catches[i])
})
fit <- assessment(inputs, r)
close(fit$K, K, 1e-4)
close(fit$q * K, 1, 1e-4)
stopifnot(fit$convergence == 0, fit$log_index_SSE < 1e-8,
          is.finite(fit$objective_gradient_logK), fit$gradient_check == "Pass",
          abs(fit$projected_gradient_logK) <= fit$gradient_tolerance,
          fit$balance_check == "Pass", fit$balance_residual_t <= fit$balance_tolerance_t,
          fit$K >= fit$bounds$lower_K, fit$K <= fit$bounds$upper_K,
          all(rows_values(fit$series, "biomass_t") > 0), !fit$boundary_fit)
objective <- function(p) schaefer_objective(p$logK, index, catches, r)
tape <- RTMB::MakeADFun(objective, list(logK = log(K * 1.2)), silent = TRUE)
x <- tape$par
h <- 1e-5
finite_difference <- (tape$fn(x + h) - tape$fn(x - h)) / (2 * h)
close(tape$gr(x), finite_difference, 1e-5)
rejects(assessment(lapply(inputs, function(row) { row$catch_t <- 0; row }), r))
flat <- assessment(lapply(inputs, function(row) { row$index <- 1; row }), r)
stopifnot(flat$boundary_fit, flat$active_bound == "upper",
          flat$objective_gradient_logK < 0, flat$projected_gradient_logK == 0,
          flat$gradient_check == "Pass")

# Terminal catch enters the future stock once; all rules share actual saved errors.
assessments <- setNames(rep(list(fit), 4), MSE_CASES)
prepared <- mse_prepare(assessments)
stopifnot(identical(prepared$error_streams, mse_prepare(assessments)$error_streams))
last <- tail(fit$series, 1)[[1]]
expected_next <- last$biomass_t + r * last$biomass_t * (1 - last$biomass_t / fit$K) - last$catch_t
close(prepared$operating_models[[1]]$B, expected_next, 1e-5)
stopifnot(length(prepared$error_streams) == 160,
          all(vapply(prepared$error_streams, function(stream) length(stream$errors) == 15, logical(1))),
          identical(numeric_values(prepared$assumptions$scenarios[[2]]$growth_multipliers),
                    c(rep(0.7, 6), rep(1, 9))))
constant <- mse_simulate(prepared, "constant")
index_rule <- mse_simulate(prepared, "index")
buffered <- mse_simulate(prepared, "buffered", 0.8)
stopifnot(identical(constant$error_streams, index_rule$error_streams),
          identical(index_rule$error_streams, buffered$error_streams),
          constant$metrics$trials == 160, length(constant$series) == 15)
for (result in list(constant, index_rule, buffered)) {
  rows <- result$example$rows
  stopifnot(all(rows_values(rows, "catch_t") <= 0.4 * rows_values(rows, "biomass_t") + 1e-8),
            all(rows_values(rows, "B_over_K") > 0))
}
stopifnot(!isTRUE(all.equal(rows_values(constant$example$rows, "observed_index"),
                           rows_values(index_rule$example$rows, "observed_index"))))
advice <- c(buffered$example$reference_catch_t,
            rows_values(buffered$example$rows, "requested_catch_t"))
stopifnot(all(abs(diff(advice) / advice[-length(advice)]) <= 0.15 + 1e-10))
# Deliberately excessive advice and growth exercise both realised-state caps.
stress_model <- prepared$operating_models[[1]]
stress_model$reference_catch_t <- 1e9
stress_errors <- rep(list(list(growth = 1e6, observation = 1)), 15)
stress <- mse_trial(stress_model, "constant", prepared$assumptions$scenarios[[1]],
                    prepared$assumptions, stress_errors)
close(rows_values(stress$rows, "catch_t"), 0.4 * rows_values(stress$rows, "biomass_t"))
stopifnot(all(rows_values(stress$rows, "growth_rate") == 1),
          all(rows_values(stress$rows, "B_over_K") > 0 & rows_values(stress$rows, "B_over_K") <= 1))
summary <- mse_summarise(list(constant, index_rule, buffered))
stopifnot(length(summary$metrics) == 3, length(summary$scenarios) == 2)
changed <- index_rule
changed$error_streams[[1]]$errors[[1]]$growth <- changed$error_streams[[1]]$errors[[1]]$growth + 0.1
rejects(mse_summarise(list(constant, changed, buffered)))

# Exercise the real driver: scalar array elements must not gain singleton arrays.
# Regression for the CI defect where vessel strings became unhashable lists.
stopifnot(is.null(names(json_array(character()))),
          is.null(names(json_array("one"))), !is.null(names(empty_object())))
encoded <- driver$workflow_encode(list(
  vessels = array(c("A", "B")), returned = list("id"), one = array(1),
  empty = list(), empty_vector = array(numeric()),
  rows = list(list(year = 2024, vessel = "A")), settings = empty_object()))
decoded <- jsonlite::fromJSON(encoded, simplifyVector = FALSE)
stopifnot(identical(decoded$vessels, list("A", "B")),
          identical(decoded$returned, list("id")),
          length(decoded$one) == 1, is.numeric(decoded$one[[1]]), decoded$one[[1]] == 1,
          grepl('"one":[1]', encoded, fixed = TRUE),
          identical(decoded$empty, list()), identical(decoded$empty_vector, list()),
          length(decoded$rows) == 1, is.list(decoded$rows[[1]]),
          is.numeric(decoded$rows[[1]]$year), decoded$rows[[1]]$year == 2024,
          identical(decoded$rows[[1]]$vessel, "A"),
          grepl('"settings":{}', encoded, fixed = TRUE))
rejects(driver$workflow_encode(list(matrix = matrix(1:4, nrow = 2))))
cat("R GLM, RTMB, timing, paired-trial and serialization sanity checks passed.\n")
