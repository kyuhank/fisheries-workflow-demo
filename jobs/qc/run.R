# Correct from the raw supplied rows; the coordinator saves the returned submission.
calculate <- function(context) {
  submission <- context$parents$submission
  invalid <- Filter(function(row) row$hooks <= 0 || row$catch_n < 0, submission$sets)
  returned <- json_array(rows_values(invalid, "set_id"))
  if (length(invalid) > 0) {
    submission <- source_rows(context$source, context$settings$last_year)
  }
  check_sets(submission$sets)
  result <- list(returned = returned, rows = length(submission$sets), checks = list(
    list(check = "Positive effort", result = "Pass"),
    list(check = "Non-negative catch", result = "Pass"),
    list(check = "Unique observation IDs", result = "Pass")))
  if (length(invalid) > 0) {
    attr(result, "workflow_effects") <- list(resubmit_submission = submission)
  }
  result
}
