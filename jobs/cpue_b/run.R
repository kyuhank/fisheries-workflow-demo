# Quarter-adjusted comparison on public rows; synthetic fixtures retain year only.
calculate <- function(context) {
  cpue(context$parents$extract$sets, vessel_effect = FALSE, stratum_effect = FALSE)
}
