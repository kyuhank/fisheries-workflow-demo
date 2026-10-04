# These rows must come from the coordinator's real snapshot SQLite queries.
calculate <- function(context) {
  extracted <- context$extracted
  require_condition(!is.null(extracted) && is.character(extracted$sql),
                    "The saved SQLite extraction input is missing.")
  check_sets(extracted$sets)
  check_catches(extracted$catch)
  list(sets = extracted$sets, catch = extracted$catch, sql = extracted$sql)
}
