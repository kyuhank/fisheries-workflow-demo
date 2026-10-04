# Compare rules only when their stocks, scenarios and actual error vectors match.
calculate <- function(context) {
  mse_summarise(context$parents[c("mse_constant", "mse_index", "mse_buffered")])
}
