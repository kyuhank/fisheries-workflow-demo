# Readable toy analyses: Poisson GLM CPUE and a one-parameter Schaefer fit.

describe_data <- function(sets, catches) {
  check_sets(sets)
  check_catches(catches)
  vessels <- sort(unique(rows_values(sets, "vessel")))
  years <- sort(unique(rows_values(sets, "year")))
  annual <- lapply(years, function(year) {
    rows <- Filter(function(row) row$year == year, sets)
    catch <- catches[[match(year, rows_values(catches, "year"))]]$catch_t
    counts <- setNames(lapply(vessels, function(vessel) {
      sum(rows_values(rows, "vessel") == vessel)
    }), vessels)
    list(year = year, observations = length(rows),
         hooks = sum(rows_values(rows, "hooks")),
         catch_n = sum(rows_values(rows, "catch_n")), catch_t = catch,
         zero_catch_percent = 100 * mean(rows_values(rows, "catch_n") == 0),
         vessels = counts)
  })
  fields <- list(
    list(name = "set_id", meaning = "Unique fishing observation", type = "text"),
    list(name = "year", meaning = "Year of fishing", type = "integer"),
    list(name = "vessel", meaning = "Synthetic vessel identifier", type = "text"),
    list(name = "hooks", meaning = "Fishing effort (hooks)", type = "integer"),
    list(name = "catch_n", meaning = "Catch in number of fish", type = "integer"))
  list(annual = annual, vessels = json_array(vessels), observations = length(sets), fields = fields)
}

cpue <- function(sets, vessel_effect = TRUE, min_hooks = 0) {
  check_sets(sets)
  rows <- Filter(function(row) row$hooks >= min_hooks, sets)
  check_sets(rows)
  years <- sort(unique(rows_values(rows, "year")))
  vessels <- sort(unique(rows_values(rows, "vessel")))
  data <- data.frame(year = factor(rows_values(rows, "year"), levels = years),
                     vessel = factor(rows_values(rows, "vessel"), levels = vessels),
                     hooks = rows_values(rows, "hooks"),
                     catch_n = rows_values(rows, "catch_n"))
  require_condition(all(tapply(data$catch_n, data$year, sum) > 0) &&
                      all(tapply(data$catch_n, data$vessel, sum) > 0),
                    "The illustrative GLM requires positive annual and vessel totals.")
  formula <- if (vessel_effect && length(vessels) > 1) {
    catch_n ~ year + vessel + offset(log(hooks / 1000))
  } else {
    catch_n ~ year + offset(log(hooks / 1000))
  }
  fit <- stats::glm(formula, data = data, family = stats::poisson(),
                    control = stats::glm.control(epsilon = 1e-10, maxit = 100))
  require_condition(fit$converged, "The CPUE GLM did not converge.")
  reference <- data.frame(year = factor(years, levels = years),
                          vessel = factor(vessels[1], levels = vessels), hooks = 1000)
  predicted <- as.numeric(stats::predict(fit, newdata = reference, type = "response"))
  index <- predicted / predicted[1]
  residual <- max(abs(tapply(stats::fitted(fit), data$year, sum) /
                       tapply(data$catch_n, data$year, sum) - 1))
  require_condition(all(is.finite(index) & index > 0) && residual < 1e-7,
                    "The CPUE GLM score check failed.")
  list(series = lapply(seq_along(years), function(i) list(year = years[i], index = index[i])),
       sets_used = length(rows), sets_excluded = length(sets) - length(rows),
       method = if (vessel_effect) "Poisson GLM: year + vessel" else "Poisson GLM: year only",
       iterations = fit$iter, converged = fit$converged,
       deviance = fit$deviance, score_residual = residual,
       reference_vessel = vessels[1], effort_unit = "1000 hooks")
}

# B[t] is biomass before that year's catch; the final element is next year's state.
surplus_path <- function(K, r, catches) {
  B <- rep(K, length(catches) + 1L)
  for (t in seq_along(catches)) {
    B[t + 1L] <- B[t] + r * B[t] * (1 - B[t] / K) - catches[t]
  }
  B
}

# Keep the taped objective entirely inside its positive-biomass domain.
capacity_bounds <- function(r, catches) {
  feasible <- function(K) {
    B <- surplus_path(K, r, catches)
    all(is.finite(B) & B > K * 1e-6)
  }
  upper <- max(100000, max(catches) * 500)
  require_condition(feasible(upper), "No feasible Schaefer trajectory within the declared bounds.")
  lo <- 1
  hi <- upper
  for (i in seq_len(40)) {
    middle <- (lo + hi) / 2
    if (feasible(middle)) hi <- middle else lo <- middle
  }
  lower <- hi * 1.001
  require_condition(lower < upper, "No interior feasible capacity interval.")
  c(lower = lower, upper = upper)
}

schaefer_objective <- function(logK, indices, catches, r) {
  K <- exp(logK)
  B <- surplus_path(K, r, catches)[seq_along(catches)]
  difference <- log(indices) - log(B)
  logq <- sum(difference) / length(difference)
  sum((difference - logq)^2)
}

assessment <- function(inputs, r) {
  require_condition(requireNamespace("RTMB", quietly = TRUE),
                    "RTMB is required; run this job in the declared R container.")
  check_row_fields(inputs, c("year", "index", "catch_t"))
  require_condition(all(vapply(inputs, function(row) {
    is.numeric(row$year) && is.numeric(row$index) && is.numeric(row$catch_t)
  }, logical(1))), "Assessment rows require numeric years, indices and catches.")
  indices <- rows_values(inputs, "index")
  catches <- rows_values(inputs, "catch_t")
  years <- rows_values(inputs, "year")
  require_condition(length(inputs) >= 3 && all(diff(years) == 1),
                    "Assessment inputs must include consecutive annual rows.")
  require_condition(all(is.finite(indices) & indices > 0) &&
                      all(is.finite(catches) & catches >= 0) && max(catches) > 0 && r > 0 && r < 1,
                    "Assessment requires positive indices, non-negative catches and 0 < r < 1.")
  bounds <- capacity_bounds(r, catches)
  objective <- function(parameters) {
    # q is profiled, not another free parameter.
    schaefer_objective(parameters$logK, indices, catches, r)
  }
  start <- min(bounds["upper"] * 0.9,
               max(bounds["lower"] * 1.2, 4 * mean(catches) / r))
  model <- RTMB::MakeADFun(objective, list(logK = log(start)), silent = TRUE)
  fit <- stats::nlminb(model$par, model$fn, model$gr,
                       lower = log(bounds["lower"]), upper = log(bounds["upper"]),
                       control = list(iter.max = 100, eval.max = 200, rel.tol = 1e-10))
  require_condition(fit$convergence == 0, paste("Schaefer fit failed:", fit$message))
  objective_value <- as.numeric(model$fn(fit$par))
  gradient <- as.numeric(model$gr(fit$par))
  require_condition(is.finite(objective_value) && length(gradient) == 1 && is.finite(gradient),
                    "The fitted objective or gradient is not finite.")
  active_bound <- if (fit$par[1] <= log(bounds["lower"]) + 1e-7) "lower" else
    if (fit$par[1] >= log(bounds["upper"]) - 1e-7) "upper" else "none"
  # At a constrained optimum the gradient may point out of the allowed interval.
  projected_gradient <- switch(active_bound, lower = min(gradient, 0),
                                upper = max(gradient, 0), none = gradient)
  gradient_tolerance <- 1e-4
  K <- unname(exp(fit$par[1]))
  path <- surplus_path(K, r, catches)
  B <- path[seq_along(catches)]
  require_condition(all(is.finite(path) & path > 0), "The fitted Schaefer path is not feasible.")
  balance <- diff(path) - r * B * (1 - B / K) + catches
  balance_residual <- max(abs(balance))
  balance_tolerance <- 1e-8 * max(1, catches)
  require_condition(balance_residual <= balance_tolerance,
                    "The declared annual biomass recurrence does not balance.")
  q <- exp(mean(log(indices) - log(B)))
  predicted <- q * B
  series <- lapply(seq_along(years), function(i) {
    list(year = years[i], observed_index = indices[i], fitted_index = predicted[i],
         log_residual = log(indices[i] / predicted[i]),
         B_over_K = B[i] / K, harvest_rate = catches[i] / B[i],
         biomass_t = B[i], catch_t = catches[i])
  })
  list(series = series, r = r, K = K, q = q, initial_B_over_K = 1,
       next_biomass_t = unname(tail(path, 1)), feasibility_check = "Pass",
       balance_residual_t = balance_residual, balance_tolerance_t = balance_tolerance,
       balance_check = "Pass", catch_check = "Pass",
       fit_method = "RTMB::MakeADFun + nlminb", convergence = fit$convergence,
       objective_value = objective_value, objective_gradient_logK = gradient,
       projected_gradient_logK = projected_gradient, active_bound = active_bound,
       gradient_tolerance = gradient_tolerance,
       gradient_check = if (abs(projected_gradient) <= gradient_tolerance) "Pass" else "Review",
       log_index_SSE = sum(log(indices / predicted)^2),
       boundary_fit = K <= bounds["lower"] * 1.001 || K >= bounds["upper"] / 1.001,
       bounds = list(lower_K = unname(bounds["lower"]), upper_K = unname(bounds["upper"])),
       assumptions = json_array(c("Schaefer annual surplus production; initial biomass is K.",
                             "Intrinsic growth is fixed within each sensitivity case.",
                             "Only K is estimated; q is profiled from log-index residuals.",
                             "Balance checks test the declared recurrence, not an independent fit to catches.",
                             "No confidence intervals or real-stock validation are supplied.")))
}
