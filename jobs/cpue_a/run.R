# Public aggregate data: year and cell–quarter effects with an effort offset.
# Synthetic inputs retain the original year/vessel Poisson example.
calculate <- function(context) {
  cpue(context$parents$extract$sets, vessel_effect = TRUE, stratum_effect = TRUE,
       min_hooks = context$settings$min_hooks_a)
}
