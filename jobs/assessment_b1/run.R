# Fit one log(K) with RTMB; growth and initial B/K are fixed for this case.
calculate <- function(context) {
  assessment(context$parents$prepare_b$rows, r = 0.25)
}
