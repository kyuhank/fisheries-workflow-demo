# Join index A to annual removals by year before fitting the stock model.
calculate <- function(context) {
  prepare_inputs(context$parents$cpue_a$series, context$parents$extract$catch)
}
