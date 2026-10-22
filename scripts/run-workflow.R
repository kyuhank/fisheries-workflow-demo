#!/usr/bin/env Rscript
# Entry point for the host R coordinator. Calculations run through component Makefiles.
args <- commandArgs(trailingOnly = TRUE)
script_arg <- commandArgs()[startsWith(commandArgs(), "--file=")]
root <- normalizePath(file.path(dirname(sub("^--file=", "", script_arg[[1L]])), ".."), mustWork = TRUE)
options(workflow.root = root)
source(file.path(root, "R/sources.R"))
source(file.path(root, "R/inputs.R"))
source(file.path(root, "R/workflow.R"))
if (file.exists(file.path(root, "R/runtime.R"))) source(file.path(root, "R/runtime.R"))
command <- if (length(args) && !startsWith(args[[1L]], "--")) args[[1L]] else "run"
if (length(args) && identical(args[[1L]], command)) args <- args[-1L]
options_cli <- list(output = "runs", start = "submission", scope = "workflow", source_lock = "source-lock.json",
                    settings = NULL, bundle = NULL, reference = "reference", offline = FALSE, local_root = NULL,
                    max_workers = 4L, tolerance = 1e-8, local = FALSE)
while (length(args)) {
  flag <- args[[1L]]
  name <- gsub("-", "_", sub("^--", "", flag))
  if (!startsWith(flag, "--") || !name %in% names(options_cli)) stop("Unknown option: ", flag)
  if (name %in% c("offline", "local")) { options_cli[[name]] <- TRUE; args <- args[-1L]; next }
  if (length(args) < 2L) stop("Missing value: ", flag)
  options_cli[name] <- list(args[[2L]]); args <- args[-c(1L, 2L)]
}
if (command == "hydrate") {
  hydrate_sources(root, lock = if (options_cli$source_lock == "source-lock.json") "source-lock.template.json" else options_cli$source_lock,
                  local_root = options_cli$local_root)
  quit(status = 0L)
}
if (!command %in% c("run", "plan", "bundle", "compare")) stop("Choose run, plan, bundle, compare or hydrate")
settings <- if (is.null(options_cli$settings)) list() else json_read(options_cli$settings)
if (isTRUE(options_cli$offline)) Sys.setenv(PAPER_OFFLINE = "1")
execution <- list(max_workers = as.integer(options_cli$max_workers), offline = isTRUE(options_cli$offline), local = isTRUE(options_cli$local))
workflow <- new_workflow(options_cli$output, settings = settings, source_lock = options_cli$source_lock, execution = execution,
  notify = function(event, state, output = NULL) {
    if (!is.null(event$job)) cat(event$job, event$state, event$message, "\n", file = stderr())
  }, handover = NULL)
if (command == "plan") {
  cat(json_encode(workflow_plan(workflow, options_cli$start, options_cli$scope), pretty = TRUE), "\n")
} else if (command == "run") {
  result <- workflow_run(workflow, options_cli$start, options_cli$scope)
  if (!is.null(options_cli$bundle)) workflow_bundle(workflow, options_cli$bundle)
  cat(json_encode(list(run_id = result$run_id, run = result$run, retained = result$retained), pretty = TRUE), "\n")
} else if (command == "bundle") {
  workflow_bundle(workflow, options_cli$bundle %||% "workflow.zip")
} else {
  reference <- json_read(file.path(options_cli$reference, "state.json"))
  keys <- if (options_cli$scope == "job") options_cli$start else names(reference$records)
  for (key in keys) {
    actual <- json_read(file.path(options_cli$output, key, "output.json"))
    expected <- json_read(file.path(options_cli$reference, key, "output.json"))
    comparison <- all.equal(actual, expected, tolerance = as.numeric(options_cli$tolerance), check.attributes = TRUE)
    if (!isTRUE(comparison)) stop("Numerical output differs for ", key, ": ", paste(comparison, collapse = "; "))
  }
  cat("Compared", length(keys), "saved numerical outputs.\n")
}
