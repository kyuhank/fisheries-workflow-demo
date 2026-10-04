# QC is the scheduling gate; accepted submission rows are the calculation input.
# The coordinator writes these same rows to the SQLite snapshot.
calculate <- function(context) {
  accepted <- context$parents$submission
  years <- rows_values(accepted$sets, "year")
  summary <- describe_data(accepted$sets, accepted$catch)
  c(list(rows = length(years), first_year = min(years), last_year = max(years)), summary)
}
