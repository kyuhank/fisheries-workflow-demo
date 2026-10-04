# Hold annual advice at recent mean catch in the common management trials.
calculate <- function(context) {
  mse_simulate(context$parents$mse_prepare, rule = "constant")
}
