# Alternative Poisson GLM with year effects and the same effort offset.
calculate <- function(context) {
  cpue(context$parents$extract$sets, vessel_effect = FALSE)
}
