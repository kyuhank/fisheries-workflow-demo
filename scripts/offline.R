#!/usr/bin/env Rscript
# Verify preserved sources and locally restored images before reproduction.
offline_catalogue <- function(root) {
  value <- json_read(file.path(root, "runtime-catalogue.json"))
  if (!identical(value$schema_version, 2L) || !is.list(value$images) || !length(value$images)) stop("Invalid runtime catalogue")
  for (image in value$images) {
    if (!grepl("^([A-Za-z0-9][A-Za-z0-9._:/-]*@)?sha256:[a-f0-9]{64}$", image$image %||% "") ||
        !grepl("^sha256:[a-f0-9]{64}$", image$image_id %||% "") ||
        !grepl("^[a-z0-9]+/[a-z0-9_]+(/[a-z0-9]+)?$", image$platform %||% "") ||
        !is.list(image$rootfs_diff_ids) || !length(image$rootfs_diff_ids) ||
        !all(grepl("^sha256:[a-f0-9]{64}$", unlist(image$rootfs_diff_ids))) || !length(image$uses)) stop("Incomplete runtime identity")
    source_path(root, image$archive, exists = FALSE)
  }
  state <- json_read(file.path(root, "reference/state.json"))
  for (key in names(state$records)) for (role in c("calculation", "rendering")) {
    record <- state$records[[key]]
    runtime <- if (role == "rendering") record$report_rendering$runtime %||% record$runtime else record$runtime
    matches <- Filter(function(image) identical(image$image, runtime$image) && identical(image$image_id, runtime$image_id) &&
      identical(image$platform, runtime$platform) && identical(unlist(image$rootfs_diff_ids), unlist(runtime$rootfs_diff_ids)) &&
      any(vapply(image$uses, function(use) identical(use$job, key) && identical(use$role, role) && identical(use$run_id, record$run_id), logical(1))), value$images)
    if (length(matches) != 1L) stop("Runtime catalogue omits or duplicates a producing identity: ", key, " ", role)
  }
  value
}
offline_image <- function(image) runtime_image(image$image_id, image$platform, pull = "never", preserved = image)
offline_archives <- function(root, directory, mode) {
  catalogue <- offline_catalogue(root)
  dir.create(directory, recursive = TRUE, showWarnings = FALSE)
  directory <- normalizePath(directory, mustWork = TRUE)
  receipt_path <- file.path(directory, "runtime-archives.json")
  if (mode == "save") {
    for (image in catalogue$images) offline_image(image)
    receipts <- list()
    for (image in catalogue$images) if (is.null(receipts[[image$archive]])) {
      destination <- source_path(directory, image$archive, exists = FALSE)
      dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)
      runtime_checked("docker", c("image", "save", "--output", destination, image$image_id), timeout = 180)
      receipts[[image$archive]] <- c(image[c("image_id", "platform", "rootfs_diff_ids")], list(sha256 = file_sha256(destination)))
    }
    json_write(list(schema_version = 1L, catalogue_sha256 = file_sha256(file.path(root, "runtime-catalogue.json")), archives = receipts), receipt_path)
    json_write(c(lapply(receipts, function(receipt) receipt$sha256), list("runtime-archives.json" = file_sha256(receipt_path))), file.path(directory, "SHA256SUMS.json"))
  } else {
    receipt <- json_read(receipt_path); sums <- json_read(file.path(directory, "SHA256SUMS.json"))
    if (!identical(receipt$schema_version, 1L) || !identical(receipt$catalogue_sha256, file_sha256(file.path(root, "runtime-catalogue.json"))) ||
        !identical(file_sha256(receipt_path), sums[["runtime-archives.json"]])) stop("Runtime archive receipt differs")
    for (image in catalogue$images) {
      saved <- receipt$archives[[image$archive]]
      if (is.null(saved) || !identical(saved$image_id, image$image_id) || !identical(saved$platform, image$platform) ||
          !identical(unlist(saved$rootfs_diff_ids), unlist(image$rootfs_diff_ids)) || !identical(saved$sha256, sums[[image$archive]]) ||
          !identical(file_sha256(source_path(directory, image$archive)), saved$sha256)) stop("Runtime archive checksum or identity differs: ", image$archive)
    }
    if (mode == "load") for (name in unique(vapply(catalogue$images, function(image) image$archive, character(1))))
      runtime_checked("docker", c("image", "load", "--input", source_path(directory, name)), timeout = 180)
    for (image in catalogue$images) offline_image(image)
  }
  cat("Verified", length(unique(vapply(catalogue$images, function(image) image$image_id, character(1)))), "preserved images.\n")
}
offline_same <- function(left, right) {
  if (is.numeric(left) && is.numeric(right)) return(identical(as.numeric(left), as.numeric(right)))
  if (is.list(left) && is.list(right)) {
    if (!identical(is.null(names(left)), is.null(names(right))) || length(left) != length(right)) return(FALSE)
    if (!is.null(names(left))) {
      if (!setequal(names(left), names(right))) return(FALSE)
      return(all(vapply(names(left), function(key) offline_same(left[[key]], right[[key]]), logical(1))))
    }
    return(all(vapply(seq_along(left), function(i) offline_same(left[[i]], right[[i]]), logical(1))))
  }
  identical(left, right)
}
offline_fit_matches <- function(expected, actual) {
  valid <- function(value) is.numeric(value$convergence) && identical(as.numeric(value$convergence), 0) &&
    identical(value$gradient_check, "Pass") && identical(as.numeric(value$gradient_tolerance), 1e-4) &&
    isTRUE(value$active_bound %in% c("none", "lower", "upper")) && identical(value$fit_method, "RTMB::MakeADFun + nlminb")
  isTRUE(valid(expected)) && isTRUE(valid(actual)) && identical(expected$active_bound, actual$active_bound)
}
offline_residuals <- function(output, path) {
  for (row in output$series) if (!is.null(row$log_residual)) {
    if (!is.numeric(row$observed_index) || row$observed_index <= 0 || !is.numeric(row$fitted_index) || row$fitted_index <= 0 ||
        !is.numeric(row$log_residual) || abs(row$log_residual - log(row$observed_index / row$fitted_index)) > 1e-12) stop("Invalid assessment residual: ", path)
  }
}
offline_compare <- function(root, output, keys) {
  required <- list(schema_version = 1L, relative = 1e-8, absolute = 1e-9, assessment_log_residual_absolute = 1e-8, near_zero_gradient = 1e-7)
  policy <- json_read(file.path(root, "comparison-policy.json"))
  for (field in names(required)) if (!identical(as.character(policy[[field]]), as.character(required[[field]]))) stop("Unsupported numerical comparison policy: ", field)
  reference <- file.path(root, "reference")
  assessments <- paste0("assessment_", c("a1", "a2", "b1", "b2"))
  titles <- setNames(assessments, paste("Assessment", c("A1", "A2", "B1", "B2")))
  direct <- list()
  if (any(keys %in% c(assessments, "assessment_summary", "assessment_report"))) for (key in assessments) {
    left <- json_read(file.path(reference, key, "output.json")); right <- json_read(file.path(output, key, "output.json"))
    offline_residuals(left, key); offline_residuals(right, key); direct[[key]] <- list(left, right)
  }
  compare <- function(left, right, path, fit = NULL) {
    if (is.list(left)) {
      if (!is.list(right) || !identical(is.null(names(left)), is.null(names(right))) || length(left) != length(right) ||
          (!is.null(names(left)) && !setequal(names(left), names(right)))) stop("JSON structure differs: ", path)
      if (!is.null(names(left))) {
        if (path %in% assessments) fit <- direct[[path]]
        if (grepl("^assessment_(summary|report)\\.diagnostics\\[[0-9]+\\]$", path)) fit <- direct[[titles[[left$case]]]]
        for (key in names(left)) {
          if (key %in% c("objective_gradient_logK", "projected_gradient_logK") && !is.null(fit) && offline_fit_matches(fit[[1L]], fit[[2L]]) &&
              is.numeric(left[[key]]) && is.numeric(right[[key]]) && max(abs(c(left[[key]], right[[key]], left[[key]] - right[[key]]))) <= policy$near_zero_gradient) next
          compare(left[[key]], right[[key]], paste(path, key, sep = "."), fit)
        }
      } else for (i in seq_along(left)) compare(left[[i]], right[[i]], paste0(path, "[", i - 1L, "]"), fit)
    } else if (is.numeric(left)) {
      absolute <- policy$absolute
      if (grepl("\\.log_residual$", path)) {
        case <- if (grepl("^assessment_[ab][12]\\.", path)) sub("\\..*$", "", path) else {
          name <- sub("^assessment_(summary|report)\\.series\\.(Assessment [AB][12])\\[.*$", "\\2", path)
          if (name %in% names(titles)) titles[[name]] else NULL
        }
        if (!is.null(case) && !is.null(direct[[case]]) && offline_fit_matches(direct[[case]][[1L]], direct[[case]][[2L]])) absolute <- policy$assessment_log_residual_absolute
      }
      if (!is.numeric(right) || length(left) != length(right) || any(abs(left - right) > pmax(absolute, policy$relative * pmax(abs(left), abs(right))))) stop("Numerical output differs: ", path)
    } else if (!identical(left, right)) stop("JSON value differs: ", path)
  }
  if (any(keys %in% c("assessment_summary", "assessment_report")))
    for (key in assessments) compare(direct[[key]][[1L]], direct[[key]][[2L]], key)
  for (key in keys) {
    left <- json_read(file.path(reference, key, "output.json")); right <- json_read(file.path(output, key, "output.json"))
    if (key == "qc") { left$returned <- NULL; right$returned <- NULL }
    if (key %in% c("assessment_summary", "assessment_report")) for (side in 1:2) {
      value <- list(left, right)[[side]]; cases <- vapply(value$diagnostics, function(row) row$case, character(1))
      if (length(cases) != 4L || !setequal(cases, names(titles)) || !setequal(names(value$series), names(titles))) stop("Invalid copied assessment cases: ", key)
      for (row in value$diagnostics) {
        source <- direct[[titles[[row$case]]]][[side]]
        if (!all(c("objective_gradient_logK", "projected_gradient_logK", "convergence", "gradient_check", "active_bound", "fit_method") %in% names(row))) stop("Missing copied diagnostics")
        for (field in setdiff(names(row), "case")) if (!offline_same(row[[field]], source[[field]])) stop("Assessment copy differs: ", key)
        if (!offline_same(value$series[[row$case]], source$series)) stop("Assessment series copy differs: ", key)
      }
    }
    compare(left, right, key)
  }
  cat(length(keys), "numerical outputs agree (relative 1e-8; absolute 1e-9; recorded diagnostic exceptions).\n")
  invisible(length(keys))
}
offline_main <- function(args = commandArgs(trailingOnly = TRUE)) {
  script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
  root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE); options(workflow.root = root)
  source(file.path(root, "R/sources.R")); source(file.path(root, "R/runtime.R")); source(file.path(root, "scripts/release.R")); workflow_require()
  if (!length(args)) stop("Use reproduce [JOB], compare [JOB], run, job JOB, check, or archive-save|archive-load|archive-verify DIRECTORY")
  command <- args[[1L]]; args <- args[-1L]; release_manifest(root)
  if (command %in% c("archive-save", "archive-load", "archive-verify")) {
    if (length(args) != 1L) stop("Supply the runtime archive directory")
    offline_archives(root, args[[1L]], sub("^archive-", "", command)); return(invisible(NULL))
  }
  if (!command %in% c("reproduce", "compare", "run", "job", "check")) stop("Unknown offline command")
  output <- Sys.getenv("PAPER_OFFLINE_OUTPUT", file.path(root, "offline-runs")); selected <- NULL
  while (length(args)) {
    if (identical(args[[1L]], "--output") && length(args) >= 2L) { output <- args[[2L]]; args <- args[-c(1L, 2L)]; next }
    if (!is.null(selected) || startsWith(args[[1L]], "--")) stop("Use one JOB and optional --output DIRECTORY")
    selected <- args[[1L]]; args <- args[-1L]
  }
  state <- json_read(file.path(root, "reference/state.json"))
  if (!identical(state$schema_version, 2L)) stop("Preserved run requires R workflow schema 2")
  if (is.null(selected) && command %in% c("reproduce", "compare") && identical(state$last_plan$scope, "job")) selected <- state$last_plan$start
  if (!is.null(selected) && !selected %in% names(state$records)) stop("Unknown saved job: ", selected)
  if (command == "job" && is.null(selected)) stop("Supply JOB")
  catalogue <- offline_catalogue(root)
  if (command != "compare") for (image in catalogue$images) offline_image(image)
  if (command == "check") { cat("Verified preserved files and every required runtime.\n"); return(invisible(NULL)) }
  output <- path.expand(output); if (!startsWith(output, "/")) output <- file.path(root, output)
  dir.create(output, recursive = TRUE, showWarnings = FALSE); output <- normalizePath(output, mustWork = TRUE)
  if (identical(output, normalizePath(file.path(root, "reference")))) stop("Choose a separate output directory")
  if (command != "compare") {
    if (command == "reproduce" && !file.exists(file.path(output, "state.json"))) {
      for (name in release_files(file.path(root, "reference"))) {
        destination <- source_path(output, name, exists = FALSE); dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)
        if (!file.copy(source_path(file.path(root, "reference"), name), destination)) stop("Cannot seed saved inputs")
      }
      if (is.null(selected)) { seeded <- state; seeded$records <- json_object(); seeded$last_plan <- NULL; json_write(seeded, file.path(output, "state.json")) }
    }
    Sys.setenv(PAPER_OFFLINE = "1", PAPER_DOCKER_PULL = "never")
    cli <- c("--vanilla", file.path(root, "scripts/run-workflow.R"), "run", "--offline", "--max-workers", "2", "--output", output,
      "--settings", file.path(root, "settings.json"), "--start", selected %||% "submission", "--scope", if (is.null(selected)) "workflow" else "job")
    if (isTRUE(state$records$submission$execution$local)) cli <- c(cli, "--local")
    result <- runtime_process(file.path(R.home("bin"), "Rscript"), cli, timeout = 3600)
    cat(result$stdout, "\n"); if (nzchar(result$stderr)) cat(result$stderr, "\n", file = stderr())
    if (result$status != 0L) stop("Preserved workflow execution failed")
  }
  if (command %in% c("reproduce", "compare")) offline_compare(root, output, selected %||% names(state$records))
}
if (sys.nframe() == 0L) offline_main()
