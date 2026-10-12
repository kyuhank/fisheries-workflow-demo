# Assemble supplied records; the invalid-effort correction is a synthetic example.
calculate <- function(context) {
  result <- source_rows(context$source, context$settings$last_year)
  require_condition(length(result$sets) > 0, "No submission records supplied.")
  if (is.null(result$sets[[1]]$stratum)) result$sets[[1]]$hooks <- 0
  result
}
