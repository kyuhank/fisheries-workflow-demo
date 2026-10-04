# Meaningful scientific sanity checks. Execute only in the authorised R container.
source("workflow/r_driver.R")
workflow_require_container()
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

# The bridge must preserve empty/one-row arrays; jsonlite alone needs this distinction.
stopifnot(is.null(names(json_array(character()))),
          is.null(names(json_array("one"))), !is.null(names(empty_object())))
one <- workflow_encode(list(rows = list(list(year = 2024)), returned = list(), settings = empty_object()))
decoded <- jsonlite::fromJSON(one, simplifyVector = FALSE)
stopifnot(length(decoded$rows) == 1, is.list(decoded$rows[[1]]), length(decoded$returned) == 0,
          is.null(names(decoded$returned)), grepl('"settings":{}', one, fixed = TRUE))
cat("R GLM, RTMB, timing, paired-trial and serialization sanity checks passed.\n")
