#!/usr/bin/env Rscript
# Preserved jobs use their producing images without changing committed settings.
script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
source(file.path(root, "R/sources.R")); source(file.path(root, "R/runtime.R"))
fixture <- tempfile("runtime-binding-"); dir.create(fixture)
image <- function(letter) paste0("example/runtime@sha256:", strrep(letter, 64L))
entry <- list(image = image("a"), platform = "linux/amd64", package_url = "https://example.org/runtime")
json_write(list(schema_version = 1L, default = entry, jobs = json_object()), file.path(fixture, "runtime.json"))
json_write(list(schema_version = 1L, jobs = list(cpue_a = list(image = image("b")), cpue_b = list(image = image("b")))), file.path(fixture, "runtime-overrides.json"))
json_write(list(schema_version = 1L, jobs = list(cpue_a = entry)), file.path(fixture, "runtime-preserved.json"))
original <- source_job
source_job <- function(sources, key) list(root = fixture, group = "cpue")
sources <- new.env(parent = emptyenv()); sources$root <- fixture
before <- file_sha256(file.path(fixture, "runtime-overrides.json"))
Sys.setenv(PAPER_OFFLINE = "0")
stopifnot(identical(runtime_binding(list(key = "cpue_a"), sources)$entry$image, image("b")))
Sys.setenv(PAPER_OFFLINE = "1")
stopifnot(identical(runtime_binding(list(key = "cpue_a"), sources)$entry$image, image("a")),
  identical(runtime_binding(list(key = "cpue_b"), sources)$entry$image, image("b")),
  identical(before, file_sha256(file.path(fixture, "runtime-overrides.json"))))
source_job <- original; unlink(fixture, recursive = TRUE)
cat("Preserved runtime selection and committed-settings custody passed. No Docker execution.\n")

# Inventory probes are process-local metadata; every calculation and PDF still
# has its own container. These fixtures replace only Docker-facing functions.
local({
  fixture <- tempfile("runtime-inventory-"); dir.create(fixture)
  on.exit(unlink(fixture, recursive = TRUE), add = TRUE)
  saved <- list(source_job = source_job, runtime_image = runtime_image, runtime_launch = runtime_launch,
    offline = Sys.getenv("PAPER_OFFLINE", unset = NA_character_))
  on.exit({
    source_job <<- saved$source_job; runtime_image <<- saved$runtime_image; runtime_launch <<- saved$runtime_launch
    rm(list = ls(.runtime_cache), envir = .runtime_cache)
    if (is.na(saved$offline)) Sys.unsetenv("PAPER_OFFLINE") else Sys.setenv(PAPER_OFFLINE = saved$offline)
  }, add = TRUE)
  sources <- new.env(parent = emptyenv()); sources$root <- fixture
  sources$repositories <- list(); sources$files <- list()
  for (group in names(source_groups)) {
    folder <- file.path(fixture, group); dir.create(file.path(folder, "R"), recursive = TRUE)
    dir.create(file.path(folder, "scripts"))
    json_write(list(schema_version = 1L, default = entry, jobs = json_object()), file.path(folder, "runtime.json"))
    json_write(list(jobs = source_groups[[group]]), file.path(folder, "SOURCE.json"))
    writeLines("info:\n\tRscript --vanilla scripts/info.R", file.path(folder, "Makefile"))
    writeLines('runtime_info_scope <- "component_environment"', file.path(folder, "R/adapter.R"))
    writeLines('source("R/adapter.R")', file.path(folder, "scripts/info.R"))
    sources$repositories[[group]] <- list(root = folder, repository = paste0("https://example.org/", group),
      commit = strrep("a", 40L))
    sources$files[[group]] <- list("R/helper.R" = strrep("a", 64L))
  }
  source_job <<- function(sources, key) {
    group <- source_group(key); repo <- sources$repositories[[group]]
    c(list(group = group), repo)
  }
  calls <- new.env(parent = emptyenv()); calls$images <- 0L; calls$probes <- 0L; calls$confirm <- TRUE
  reset <- function() {
    rm(list = ls(.runtime_cache), envir = .runtime_cache)
    calls$images <- 0L; calls$probes <- 0L
  }
  runtime_image <<- function(image, platform, pull = "missing", preserved = NULL) {
    calls$images <- calls$images + 1L
    if (!is.null(preserved) && !identical(preserved$image_id, paste0("sha256:", strrep("c", 64L))))
      stop("Fixture preserved image differs")
    list(image = image, image_kind = "registry_manifest", image_id = paste0("sha256:", strrep("c", 64L)),
      platform = platform, rootfs_diff_ids = list(paste0("sha256:", strrep("d", 64L))))
  }
  runtime_launch <<- function(root, folder, job, identity, target, timeout = 180) {
    stopifnot(identical(target, "info"))
    calls$probes <- calls$probes + 1L
    native <- list(r = "4.6.0", quarto = "1.9.37", packages = list(jsonlite = "2.0.0"))
    if (calls$confirm && runtime_inventory_scope(root) == "component_environment") native$scope <- "component_environment"
    list(stdout = json_encode(native))
  }
  prepare <- function(key) runtime_prepare(list(key = key), sources, fixture)
  failure <- function(expression, pattern) {
    error <- tryCatch({force(expression); NULL}, error = identity)
    stopifnot(inherits(error, "error"), grepl(pattern, conditionMessage(error), fixed = TRUE))
  }
  Sys.setenv(PAPER_OFFLINE = "0")
  keys <- unlist(source_groups, use.names = FALSE)
  reset(); values <- lapply(keys, prepare)
  stopifnot(length(values) == 22L, calls$probes == 3L, calls$images == 3L,
    all(vapply(values, function(value) identical(value$software$scope, "component_environment"), logical(1))))
  invisible(lapply(keys, prepare)); stopifnot(calls$probes == 3L)

  # A job-specific image, source identity or probe dependency cannot borrow a probe.
  sources$runtime_overrides <- list(cpue_b = list(image = image("b")))
  value <- prepare("cpue_b")
  stopifnot(calls$probes == 4L, identical(value$descriptor$image, image("b")))
  prepare("cpue_b"); stopifnot(calls$probes == 4L)
  sources$runtime_overrides <- NULL
  sources$repositories$cpue$commit <- strrep("b", 40L)
  value <- prepare("cpue_a"); stopifnot(calls$probes == 5L, identical(value$source$commit, strrep("b", 40L)))
  dependencies <- c("Makefile", "scripts/info.R", "R/adapter.R")
  for (index in seq_along(dependencies)) {
    path <- file.path(sources$repositories$cpue$root, dependencies[[index]])
    cat("\n# changed probe dependency\n", file = path, append = TRUE)
    prepare("cpue_a"); stopifnot(calls$probes == 5L + index)
  }
  sources$files$cpue[["R/helper.R"]] <- strrep("b", 64L)
  prepare("cpue_a"); stopifnot(calls$probes == 9L)
  sources$runtime_overrides <- list(cpue_a = list(package_url = "https://example.org/another-runtime"))
  prepare("cpue_a"); stopifnot(calls$probes == 10L)
  sources$runtime_overrides <- NULL
  sources$repositories$cpue$repository <- "https://example.org/another-cpue"
  prepare("cpue_a"); stopifnot(calls$probes == 11L)
  path <- file.path(sources$repositories$cpue$root, "SOURCE.json")
  json_write(list(jobs = rev(source_groups$cpue)), path)
  prepare("cpue_a"); stopifnot(calls$probes == 12L)
  json_write(list(jobs = setdiff(source_groups$cpue, "cpue_a")), path)
  failure(prepare("cpue_a"), "not declared")
  stopifnot(calls$probes == 12L)
  json_write(list(jobs = source_groups$cpue), path)

  # Legacy adapters remain per-job, even if all their images are identical.
  for (repo in sources$repositories) writeLines("runtime_info <- function(job = NULL) NULL", file.path(repo$root, "R/adapter.R"))
  reset(); invisible(lapply(keys, prepare)); stopifnot(calls$probes == 22L, calls$images == 22L)
  invisible(lapply(keys, prepare)); stopifnot(calls$probes == 22L)
  path <- file.path(sources$repositories$cpue$root, "R/adapter.R")
  writeLines('runtime_info_scope <- "component_environment"', path)
  calls$confirm <- FALSE; reset()
  failure(prepare("cpue_a"), "did not confirm")
  failure(prepare("cpue_b"), "did not confirm")
  stopifnot(calls$probes == 2L)
  calls$confirm <- TRUE

  # Offline identity and checksum checks happen before any cached return.
  Sys.setenv(PAPER_OFFLINE = "1")
  catalogue <- file.path(fixture, "runtime-catalogue.json")
  preserved <- list(image = entry$image, platform = entry$platform,
    image_id = paste0("sha256:", strrep("c", 64L)), rootfs_diff_ids = list(paste0("sha256:", strrep("d", 64L))))
  json_write(list(images = list(preserved)), catalogue)
  json_write(list("runtime-catalogue.json" = file_sha256(catalogue)), file.path(fixture, "SHA256SUMS.json"))
  reset(); prepare("cpue_a"); prepare("cpue_b"); stopifnot(calls$probes == 1L)
  cat(" ", file = catalogue, append = TRUE)
  failure(prepare("cpue_b"), "checksum differs")
  json_write(list("runtime-catalogue.json" = file_sha256(catalogue)), file.path(fixture, "SHA256SUMS.json"))
  prepare("cpue_b"); stopifnot(calls$probes == 1L)
  preserved$image_id <- paste0("sha256:", strrep("e", 64L))
  json_write(list(images = list(preserved)), catalogue)
  json_write(list("runtime-catalogue.json" = file_sha256(catalogue)), file.path(fixture, "SHA256SUMS.json"))
  failure(prepare("cpue_b"), "preserved image differs")
  stopifnot(calls$probes == 1L)
  Sys.setenv(PAPER_OFFLINE = "0")
  prepare("cpue_b"); stopifnot(calls$probes == 2L)
  cat("Component inventories: 22 jobs use 3 probes; legacy, identity, closure, declarations and offline checks passed. No Docker execution.\n")
})
