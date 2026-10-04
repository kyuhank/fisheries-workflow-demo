# Poisson GLM with year/vessel effects and log(hooks / 1000) offset.
calculate <- function(context) {
  cpue(context$parents$extract$sets, vessel_effect = TRUE,
       min_hooks = context$settings$min_hooks_a)
}
