# CPUE from public aggregate records, with the original synthetic example retained.

describe_data <- function(sets, catches) {
  check_sets(sets)
  check_catches(catches)
  public <- !is.null(sets[[1]]$stratum)
  group_field <- if (public) "stratum" else "vessel"
  groups <- sort(unique(rows_values(sets, group_field)))
  years <- sort(unique(rows_values(sets, "year")))
  annual <- lapply(years, function(year) {
    rows <- Filter(function(row) row$year == year, sets)
    position <- match(year, rows_values(catches, "year"))
    require_condition(!is.na(position), "A fishing year has no matching annual catch.")
    counts <- setNames(lapply(groups, function(group) {
      sum(rows_values(rows, group_field) == group)
    }), groups)
    result <- list(year = year, observations = length(rows),
         hooks = sum(rows_values(rows, "hooks")),
         catch_n = sum(rows_values(rows, "catch_n")), catch_t = catches[[position]]$catch_t,
         zero_catch_percent = 100 * mean(rows_values(rows, "catch_n") == 0))
    result[[if (public) "strata" else "vessels"]] <- counts
    if (public) {
      fleets <- sort(unique(rows_values(sets, "fleet")))
      result$fleets <- setNames(lapply(fleets, function(fleet) {
        sum(rows_values(rows, "fleet") == fleet)
      }), fleets)
    }
    result
  })
  fields <- list(
    list(name = "set_id", meaning = if (public) {
      "Unique aggregate source-row identifier (legacy field name; not a fishing set)"
    } else "Unique synthetic fishing observation", type = "text"),
    list(name = "year", meaning = "Year of fishing", type = "integer"),
    list(name = "hooks", meaning = "Fishing effort in hooks", type = "number"),
    list(name = "catch_n", meaning = "Catch in number of fish", type = "integer"))
  if (public) {
    fields <- c(fields, list(
      list(name = "fleet", meaning = "Reported fleet code", type = "text"),
      list(name = "quarter", meaning = "Calendar quarter", type = "integer"),
      list(name = "cell", meaning = "Reported five-degree spatial cell", type = "text"),
      list(name = "stratum", meaning = "Spatial cell and quarter", type = "text")))
  } else {
    fields <- c(fields, list(
      list(name = "vessel", meaning = "Synthetic vessel identifier", type = "text")))
  }
  result <- list(annual = annual, groups = json_array(groups), grouping_field = group_field,
                 observations = length(sets), fields = fields,
                 data_kind = if (public) "public-wcpfc" else "synthetic",
                 record_unit = if (public) "Public fleet–cell–quarter aggregate record" else
                   "Synthetic fishing observation")
  result[[if (public) "strata" else "vessels"]] <- json_array(groups)
  if (public) result$fleets <- json_array(sort(unique(rows_values(sets, "fleet"))))
  result
}

cpue_public <- function(sets, stratum_effect = TRUE, min_hooks = 0) {
  check_sets(sets)
  require_condition(length(unique(rows_values(sets, "fleet"))) == 1L,
                    "This aggregate CPUE model requires one selected fleet.")
  require_condition(is.logical(stratum_effect) && length(stratum_effect) == 1L &&
                      !is.na(stratum_effect), "Stratum adjustment must be TRUE or FALSE.")
  require_condition(is.numeric(min_hooks) && length(min_hooks) == 1L &&
                      is.finite(min_hooks) && min_hooks >= 0,
                    "The effort filter must be one finite non-negative number.")
  years <- sort(unique(rows_values(sets, "year")))
  strata <- sort(unique(rows_values(sets, "stratum")))
  rows <- Filter(function(row) row$hooks >= min_hooks, sets)
  check_sets(rows)
  require_condition(all(years %in% rows_values(rows, "year")) &&
                      all(strata %in% rows_values(rows, "stratum")),
                    "The effort filter removed a year or stratum from the fixed prediction support.")
  data <- data.frame(year = rows_values(rows, "year"),
                     stratum = rows_values(rows, "stratum"),
                     hooks = rows_values(rows, "hooks"), catch_n = rows_values(rows, "catch_n"))
  annual_catch <- tapply(data$catch_n, data$year, sum)
  stratum_catch <- tapply(data$catch_n, data$stratum, sum)
  require_condition(length(years) > 1L && all(annual_catch > 0) && all(stratum_catch > 0),
                    "The aggregate GLM requires at least two years and positive annual and stratum totals.")
  adjusted <- stratum_effect && length(strata) > 1L
  formula <- if (adjusted) {
    catch_n ~ factor(year) + factor(stratum) + offset(log(hooks / 1000))
  } else {
    catch_n ~ factor(year) + offset(log(hooks / 1000))
  }
  design <- stats::model.matrix(formula, data)
  rank <- qr(design)$rank
  require_condition(rank == ncol(design) && nrow(design) > rank,
                    "The aggregate CPUE model needs a full-rank design and residual degrees of freedom.")
  fit <- stats::glm(formula, data = data, family = stats::quasipoisson(link = "log"),
                    control = stats::glm.control(epsilon = 1e-10, maxit = 100))
  require_condition(fit$converged && all(is.finite(stats::coef(fit))),
                    "The aggregate CPUE GLM did not converge to finite coefficients.")
  # The same strata and equal weights are used in every year's response-scale mean.
  grid <- expand.grid(year = years, stratum = strata, stringsAsFactors = FALSE)
  grid$hooks <- 1000
  grid$weight <- 1 / length(strata)
  grid$predicted_cpue <- as.numeric(stats::predict(fit, newdata = grid, type = "response"))
  predicted <- vapply(years, function(year) {
    selected <- grid$year == year
    sum(grid$weight[selected] * grid$predicted_cpue[selected])
  }, numeric(1))
  nominal <- vapply(years, function(year) {
    selected <- data$year == year
    1000 * sum(data$catch_n[selected]) / sum(data$hooks[selected])
  }, numeric(1))
  index <- predicted / predicted[1]
  year_score <- max(abs(tapply(stats::fitted(fit), data$year, sum) / annual_catch - 1))
  stratum_score <- if (adjusted) {
    max(abs(tapply(stats::fitted(fit), data$stratum, sum) / stratum_catch - 1))
  } else 0
  residual <- max(year_score, stratum_score)
  dispersion <- sum(stats::residuals(fit, type = "pearson")^2) / fit$df.residual
  require_condition(all(is.finite(index) & index > 0) && residual < 1e-7 &&
                      is.finite(dispersion) && dispersion >= 0,
                    "The aggregate CPUE prediction, score or dispersion check failed.")
  list(series = lapply(seq_along(years), function(i) {
         list(year = years[i], index = index[i], standardised_cpue = predicted[i],
              nominal_cpue = nominal[i])
       }),
       sets_used = length(rows), sets_excluded = length(sets) - length(rows),
       rows_included = length(rows), rows_excluded = length(sets) - length(rows),
       released_zero_rows = sum(data$catch_n == 0), min_hooks = min_hooks,
       data_kind = "public-wcpfc", record_unit = "Public fleet–cell–quarter aggregate record",
       method = if (adjusted) "Quasipoisson GLM: year + cell–quarter stratum" else
         "Quasipoisson GLM: year only",
       formula = paste(deparse(formula, width.cutoff = 500), collapse = " "),
       iterations = fit$iter, converged = fit$converged, deviance = fit$deviance,
       dispersion = dispersion, dispersion_method = "Pearson sum of squares / residual degrees of freedom",
       rank = rank, model_columns = ncol(design), residual_degrees_of_freedom = fit$df.residual,
       score_residual = residual, year_score_residual = year_score,
       stratum_score_residual = if (adjusted) stratum_score else NULL,
       effort_unit = "Fish per 1000 hooks", prediction_effort_hooks = 1000,
       prediction_grid = lapply(seq_len(nrow(grid)), function(i) as.list(grid[i, ])),
       weights = lapply(strata, function(stratum) list(stratum = stratum, weight = 1 / length(strata))),
       standardisation = "Arithmetic mean of response-scale predictions with equal fixed stratum weights",
       normalisation = list(reference_year = years[1], divisor = predicted[1], rule = "First year = 1"),
       limitations = json_array(c(
         "Public records aggregate fleet, spatial cell and quarter; vessel identifiers are unavailable.",
         "The index covers the selected fleet and fixed released strata, not the whole stock.",
         "Released zero counts are retained; absent or suppressed source values are not zero catch.",
         "An effort filter can require additive-model predictions for omitted year–stratum cells.",
         "This demonstration supplies no confidence intervals or official assessment advice.")))
}

cpue <- function(sets, vessel_effect = TRUE, min_hooks = 0, stratum_effect = TRUE) {
  check_sets(sets)
  if (!is.null(sets[[1]]$stratum)) return(cpue_public(sets, stratum_effect, min_hooks))
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
  nominal <- vapply(years, function(year) {
    selected <- data$year == year
    1000 * sum(data$catch_n[selected]) / sum(data$hooks[selected])
  }, numeric(1))
  list(series = lapply(seq_along(years), function(i) {
         list(year = years[i], index = index[i], standardised_cpue = predicted[i], nominal_cpue = nominal[i])
       }),
       sets_used = length(rows), sets_excluded = length(sets) - length(rows),
       method = if (vessel_effect) "Poisson GLM: year + vessel" else "Poisson GLM: year only",
       data_kind = "synthetic", record_unit = "Synthetic fishing observation",
       formula = paste(deparse(formula, width.cutoff = 500), collapse = " "),
       normalisation = list(reference_year = years[1], divisor = predicted[1], rule = "First year = 1"),
       standardisation = "Prediction at the first synthetic vessel and 1000 hooks",
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
