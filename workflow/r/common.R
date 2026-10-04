# Small helpers for JSON row lists. The container driver owns files and SQLite.

json_array <- function(x) unname(as.list(x))
empty_object <- function() structure(list(), names = character())
numeric_values <- function(x) as.numeric(unlist(x, use.names = FALSE))
rows_values <- function(rows, field) {
  unlist(lapply(rows, function(row) row[[field]]), use.names = FALSE)
}
optional_value <- function(x, fallback) if (is.null(x)) fallback else x
require_condition <- function(condition, message) {
  if (!isTRUE(condition)) stop(message, call. = FALSE)
}

check_row_fields <- function(rows, fields) {
  for (row in rows) {
    require_condition(is.list(row) && !is.null(names(row)) && !anyDuplicated(names(row)),
                      "Each input row must be an object with unique field names.")
    for (field in fields) {
      value <- row[[field]]
      require_condition(length(value) == 1L && is.atomic(value) && !is.na(value),
                        paste("Each input row needs one non-missing", field, "value."))
    }
  }
}

source_rows <- function(source, last_year) {
  sets <- source$sets
  catches <- source$catch
  if (last_year == 2024 && !is.null(source$submission)) {
    fields <- c("set_id", "year", "vessel", "hooks", "catch_n")
    batch <- lapply(source$submission$sets, function(row) {
      if (is.null(names(row))) setNames(as.list(row), fields) else row
    })
    sets <- c(sets, batch)
    catches <- c(catches, list(list(year = 2024, catch_t = source$submission$catch)))
  }
  list(sets = Filter(function(row) row$year <= last_year, sets),
       catch = Filter(function(row) row$year <= last_year, catches))
}

check_sets <- function(sets) {
  require_condition(length(sets) > 0, "No fishing observations supplied.")
  check_row_fields(sets, c("set_id", "year", "vessel", "hooks", "catch_n"))
  for (row in sets) {
    require_condition(is.character(row$set_id) && nzchar(row$set_id) &&
                        is.character(row$vessel) && nzchar(row$vessel) &&
                        is.numeric(row$year) && is.finite(row$year) && row$year == floor(row$year) &&
                        is.numeric(row$hooks) && is.numeric(row$catch_n),
                      "Fishing rows need identifiers, integer years and numeric effort/counts.")
  }
  hooks <- rows_values(sets, "hooks")
  catches <- rows_values(sets, "catch_n")
  require_condition(all(is.finite(hooks) & hooks > 0 &
                        is.finite(catches) & catches >= 0 & catches == floor(catches)),
                    "Fishing observations require positive effort and non-negative integer counts.")
  identifiers <- rows_values(sets, "set_id")
  require_condition(length(unique(identifiers)) == length(sets),
                    "Duplicate observation identifiers.")
}

check_catches <- function(catches) {
  require_condition(length(catches) > 0, "No annual catches supplied.")
  check_row_fields(catches, c("year", "catch_t"))
  for (row in catches) {
    require_condition(is.numeric(row$year) && is.finite(row$year) && row$year == floor(row$year) &&
                        is.numeric(row$catch_t),
                      "Annual catch rows need integer years and numeric catches.")
  }
  values <- rows_values(catches, "catch_t")
  years <- rows_values(catches, "year")
  require_condition(all(is.finite(values) & values >= 0),
                    "Annual catches must be finite and non-negative.")
  require_condition(length(unique(years)) == length(catches),
                    "Duplicate annual catch years.")
}

prepare_inputs <- function(index, catches) {
  catch_years <- rows_values(catches, "year")
  rows <- lapply(index, function(row) {
    position <- match(row$year, catch_years)
    require_condition(!is.na(position), "A CPUE year has no matching catch.")
    c(row, list(catch_t = catches[[position]]$catch_t))
  })
  list(rows = rows)
}

compare_series <- function(results, titles, assessment = FALSE) {
  series <- setNames(lapply(results, function(result) result$series), titles)
  output <- list(series = series)
  if (assessment) {
    output$diagnostics <- lapply(seq_along(results), function(i) {
      result <- results[[i]]
      list(case = titles[i], r = result$r, K = result$K,
           convergence = result$convergence, boundary_fit = result$boundary_fit,
           balance_check = result$balance_check, balance_residual_t = result$balance_residual_t,
           feasibility_check = result$feasibility_check,
           objective_value = result$objective_value,
           objective_gradient_logK = result$objective_gradient_logK,
           projected_gradient_logK = result$projected_gradient_logK,
           gradient_check = result$gradient_check, active_bound = result$active_bound,
           catch_check = result$catch_check, fit_method = result$fit_method)
    })
  }
  output
}
