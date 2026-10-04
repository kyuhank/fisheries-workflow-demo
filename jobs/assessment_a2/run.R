# Fit one log(K) with RTMB; growth and initial B/K are fixed for this case.
calculate <- function(context) {
  assessment(context$parents$prepare_a$rows, r = context$settings$growth_rate_2)
}
