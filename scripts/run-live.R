#!/usr/bin/env Rscript
# GitHub OIDC and service credentials remain in this host process.
script <- commandArgs()[startsWith(commandArgs(), "--file=")][[1L]]
root <- normalizePath(file.path(dirname(sub("^--file=", "", script)), ".."), mustWork = TRUE)
options(workflow.root = root)
for (name in c("sources", "inputs", "workflow", "runtime", "cloud")) source(file.path(root, "R", paste0(name, ".R")))
workflow_require()
client <- new_cloud()
args <- commandArgs(trailingOnly = TRUE)
if (identical(args, "--announce")) {
  tryCatch({
    cloud_api(client, "context")
    cloud_api(client, "event", list(event = list(state = "phase", title = "Preparing the analysis software",
      message = "The GitHub runner is retrieving the pinned analysis sources and each job's assigned software.")))
  }, cloud_temporary = function(error) cat("Setup status is temporarily unavailable; continuing.\n"))
} else {
  if (length(args)) stop("Use no arguments, or --announce")
  cloud_run(client)
}
