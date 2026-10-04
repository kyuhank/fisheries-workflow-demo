# Keep both fitted index series; comparison adds no new model.
calculate <- function(context) {
  compare_series(context$parents[c("cpue_a", "cpue_b")],
                 c("CPUE analysis A", "CPUE analysis B"))
}
