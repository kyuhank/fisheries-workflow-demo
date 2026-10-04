# Update advice from the three-year mean observed index in the common trials.
calculate <- function(context) {
  mse_simulate(context$parents$mse_prepare, rule = "index")
}
