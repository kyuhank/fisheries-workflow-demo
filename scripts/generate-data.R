# Generate the declared synthetic Schaefer/Poisson example inside the R container.
# The coordinator imports this JSON into SQLite and separates the 2024 submission.
source("workflow/r_driver.R")
workflow_require_container()
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) stop("Usage: Rscript scripts/generate-data.R OUTPUT.json")
if (!requireNamespace("jsonlite", quietly = TRUE)) stop("jsonlite is required.")

seed <- 20261004L
RNGkind("Mersenne-Twister", "Inversion", "Rejection")
set.seed(seed)
years <- 2000:2024
K <- 10000
r <- 0.30
q <- 4 / K  # expected fish per 1000 hooks at the reference vessel
catch_t <- 400 + 20 * (years - years[1])
B <- rep(K, length(years) + 1L)
for (year in seq_along(years)) {
  B[year + 1L] <- B[year] + r * B[year] * (1 - B[year] / K) - catch_t[year]
}
if (!all(B > 0)) stop("The declared generating trajectory is not feasible.")

vessel_effects <- c(A = 0.8, B = 1, C = 1.2, D = 1.5)
sets <- list()
for (year in seq_along(years)) {
  for (vessel in names(vessel_effects)) {
    for (observation in 1:8) {
      hooks <- sample(c(800L, 1000L, 1400L, 1600L), 1)
      mean_count <- q * B[year] * vessel_effects[vessel] * hooks / 1000
      sets[[length(sets) + 1L]] <- list(
        set_id = sprintf("%d-%s-%02d", years[year], vessel, observation),
        year = years[year], vessel = vessel, hooks = hooks,
        catch_n = as.integer(stats::rpois(1, mean_count)))
    }
  }
}
catches <- lapply(seq_along(years), function(year) {
  list(year = years[year], catch_t = catch_t[year])
})
truth <- lapply(seq_along(years), function(year) {
  list(year = years[year], biomass_t = B[year], B_over_K = B[year] / K,
       catch_t = catch_t[year], next_biomass_t = B[year + 1L])
})
scenario <- list(
  schema_version = 1L, type = "synthetic-schaefer-poisson", seed = seed,
  generator = "R Schaefer biomass trajectory and Poisson sampled catch counts",
  rng = as.list(RNGkind()), R = R.version.string,
  parameters = list(K = K, r = r, initial_B_over_K = 1, q = q,
                    vessel_effects = as.list(vessel_effects)),
  units = list(biomass = "tonnes", annual_catch = "tonnes",
               observed_catch = "fish", effort = "hooks", CPUE = "fish per 1000 hooks"),
  snapshot_end = 2023L, submission_year = 2024L, truth = truth,
  scope = "Synthetic teaching example; not observations from a real fishery.",
  notes = list("Sampled set counts supply an abundance index, not a census of annual removals.",
               "Known annual removals and sampled CPUE share the declared biomass trajectory.",
               "Growth sensitivities and MSE perturbations illustrate assumptions; they are not validated uncertainty."))
jsonlite::write_json(list(sets = sets, catch = catches, scenario = scenario),
                     args[1], auto_unbox = TRUE, digits = 16, pretty = TRUE)
cat("Wrote synthetic JSON for coordinator import:", args[1], "\n")
