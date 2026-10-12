# Preserve both index series and the actual method and prediction support.
calculate <- function(context) {
  analyses <- context$parents[c("cpue_a", "cpue_b")]
  titles <- c("CPUE analysis A", "CPUE analysis B")
  result <- compare_series(analyses, titles)
  result$analyses <- setNames(lapply(analyses, function(analysis) {
    analysis[setdiff(names(analysis), "series")]
  }), titles)
  result$data_kind <- analyses[[1]]$data_kind
  result
}
