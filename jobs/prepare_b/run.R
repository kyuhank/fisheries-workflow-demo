# Join index B to annual removals by year before fitting the stock model.
calculate <- function(context) {
  prepare_inputs(context$parents$cpue_b$series, context$parents$extract$catch)
}
