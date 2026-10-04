# Apply index steps, the selected buffer and a 15% annual advice-change limit.
calculate <- function(context) {
  mse_simulate(context$parents$mse_prepare, rule = "buffered",
               buffer = context$settings$mse_buffer)
}
