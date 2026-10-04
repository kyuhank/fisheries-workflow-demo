# Compare fixed-growth sensitivity cases without refitting them.
calculate <- function(context) {
  keys <- c("assessment_a1", "assessment_a2", "assessment_b1", "assessment_b2")
  compare_series(context$parents[keys],
                 c("Assessment A1", "Assessment A2", "Assessment B1", "Assessment B2"),
                 assessment = TRUE)
}
