# Assemble supplied rows in R, then introduce the demonstration's invalid effort.
calculate <- function(context) {
  result <- source_rows(context$source, context$settings$last_year)
  require_condition(length(result$sets) > 0, "No submission observations supplied.")
  result$sets[[1]]$hooks <- 0
  result
}
