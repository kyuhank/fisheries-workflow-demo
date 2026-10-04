# One small JSON bridge for Rscript inside the declared Docker container.
# The analysis itself is readable in jobs/<job>/run.R and workflow/r/*.R.

workflow_require_container <- function() {
  if (!any(file.exists(c("/.dockerenv", "/run/.containerenv")))) {
    stop("New workflow calculations require the declared Docker container")
  }
  image <- Sys.getenv("PAPER_RUNTIME_IMAGE")
  if (!grepl("^[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}$", image)) {
    stop("PAPER_RUNTIME_IMAGE must identify the actual resolved container digest")
  }
  invisible(image)
}

workflow_runtime_info <- function() {
  workflow_require_container()
  required <- c("jsonlite", "RTMB", "TMB", "knitr", "rmarkdown")
  for (package in required) {
    if (!requireNamespace(package, quietly = TRUE)) stop(package, " is required")
  }
  quarto <- Sys.which("quarto")
  if (!nzchar(quarto)) stop("Quarto is required")
  version <- system2(quarto, "--version", stdout = TRUE, stderr = TRUE)
  if (!is.null(attr(version, "status")) || length(version) != 1L) {
    stop("Could not verify the Quarto version")
  }
  versions <- lapply(required, function(package) as.character(utils::packageVersion(package)))
  names(versions) <- required
  c(list(r = as.character(getRversion()), r_platform = R.version$platform,
         quarto = version), versions)
}

# Named lists are JSON objects, unnamed lists are arrays. Scalar named fields
# are unboxed; job scripts use unnamed lists for arrays with zero or one item.
workflow_json_value <- function(value, object_field = FALSE) {
  if (is.list(value)) {
    object <- !is.null(names(value))
    result <- lapply(value, workflow_json_value, object_field = object)
    if (object) names(result) <- names(value)
    return(result)
  }
  if (is.numeric(value) && any(!is.finite(value))) stop("Non-finite R output")
  if (object_field && length(value) == 1L && is.null(dim(value))) return(jsonlite::unbox(value))
  value
}

workflow_encode <- function(value) {
  as.character(jsonlite::toJSON(workflow_json_value(value), auto_unbox = FALSE,
                               digits = NA, null = "null", na = "null"))
}

workflow_execute_json <- function(input_json, root = getwd()) {
  workflow_require_container()
  # The coordinator verifies all runtime versions once; each job reads JSON here.
  if (!requireNamespace("jsonlite", quietly = TRUE)) stop("jsonlite is required")
  context <- jsonlite::fromJSON(input_json, simplifyVector = FALSE)
  key <- context$key
  if (length(key) != 1L || !grepl("^[a-z][a-z0-9_]+$", key)) stop("Invalid job key")
  job <- file.path(root, "jobs", key, "run.R")
  if (!file.exists(job)) stop("Missing R job source: ", key)
  environment <- new.env(parent = globalenv())
  shared <- list.files(file.path(root, "workflow", "r"), pattern = "\\.R$", full.names = TRUE)
  common <- file.path(root, "workflow", "r", "common.R")
  if (!common %in% shared) stop("Missing shared R contract")
  shared <- c(common, file.path(root, "workflow", "r", "models.R"),
              file.path(root, "workflow", "r", "mse.R"))
  if (!all(file.exists(shared))) stop("Missing shared R source")
  for (path in shared) source(path, local = environment, echo = FALSE)
  source(job, local = environment, echo = FALSE)
  if (!is.function(environment$calculate)) stop("R job does not define calculate(context)")
  result <- environment$calculate(context)
  effects <- attr(result, "workflow_effects", exact = TRUE)
  attr(result, "workflow_effects") <- NULL
  if (is.null(effects)) effects <- structure(list(), names = character())
  workflow_encode(list(result = result, effects = effects))
}

# Rscript reads exactly one JSON request from stdin and prints one response.
if (sys.nframe() == 0L) {
  args <- commandArgs(trailingOnly = TRUE)
  if (identical(args, "--info")) {
    cat(workflow_encode(workflow_runtime_info()))
  } else {
    input <- paste(readLines(file("stdin"), warn = FALSE), collapse = "\n")
    cat(workflow_execute_json(input))
  }
}
