# Year-only comparison with the same effort offset and first-year normalisation.
calculate <- function(context) {
  cpue(context$parents$extract$sets, vessel_effect = FALSE, stratum_effect = FALSE)
}
