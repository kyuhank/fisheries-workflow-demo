#!/usr/bin/env Rscript
# Contract tests use explicit runtime doubles; they make no scientific or image claims.
script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
repo <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
source(file.path(repo, "R/sources.R")); source(file.path(repo, "R/inputs.R")); source(file.path(repo, "R/workflow.R"))
workflow_require()
fixture <- tempfile("r-workflow-test-"); dir.create(fixture)
Sys.setenv(PAPER_DATA_MODE = "synthetic")
options(workflow.root = fixture)
copy_file <- function(from, to) {
  dir.create(dirname(to), recursive = TRUE, showWarnings = FALSE)
  if (!file.copy(from, to, overwrite = TRUE)) stop("Cannot create test fixture")
}
for (name in c("R/sources.R", "R/inputs.R", "R/workflow.R", "workflow/jobs.json", "workflow/extract.sql", "workflow/extract-public.sql", "workflow/extract-catch.sql")) copy_file(file.path(repo, name), file.path(fixture, name))
if (file.exists(file.path(repo, "R/runtime.R"))) copy_file(file.path(repo, "R/runtime.R"), file.path(fixture, "R/runtime.R")) else writeLines("# Explicit runtime double", file.path(fixture, "R/runtime.R"))
rows <- lapply(2021:2023, function(year) list(set_id = paste0("s", year), year = year, vessel = "A", hooks = 1000L, catch_n = 10L))
catches <- lapply(2021:2023, function(year) list(year = year, catch_t = 100))
json_write(list(sets = rows, catch = catches), file.path(fixture, "data/frozen-source.json"))
lock <- json_read(file.path(repo, "source-lock.template.json")); origins <- list()
files <- c("Makefile", "runtime.json", "SOURCE.json", "R/common.R", "R/adapter.R", "R/runtime.R", "R/render.R", "scripts/run-job.R", "scripts/render.R", "reports/results.qmd")
for (group in names(source_groups)) {
  spec <- lock$repositories[[group]]; target <- file.path(fixture, "components", group)
  lock$repositories[[group]]$checkout <- paste0("components/", group)
  names <- c(files, paste0("R/", group, ".R"), paste0("jobs/", source_groups[[group]], "/run.R"), paste0("jobs/", tail(source_groups[[group]], 1L), "/report.qmd"))
  for (name in names) {
    path <- file.path(target, name); dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
    if (name == "runtime.json") json_write(list(schema_version = 1L, default = list(image = paste0("example/test@sha256:", strrep("1", 64L)), platform = "linux/amd64", package_url = ""), jobs = json_object()), path)
    else writeLines(paste("# Test fixture", name), path)
    origins[[paste0("components/", group, "/", name)]] <- list(repository = spec$repository, commit = spec$commit, path = name, sha256 = file_sha256(path))
  }
}
lock$snapshot_manifest <- "source-origins.json"
json_write(lock, file.path(fixture, "source-lock.json"))
json_write(list(schema_version = 1L, sources = origins), file.path(fixture, "source-origins.json"))
backend <- list(
  prepare = function(job, sources, output) {
    binding <- json_read(file.path(source_job(sources, job$key)$root, "runtime.json"))
    effective <- utils::modifyList(binding$default, binding$jobs[[job$key]] %||% list())
    descriptor <- c(effective, list(image_id = sub(".*@", "", effective$image), rootfs_diff_ids = list(paste0("sha256:", strrep("a", 64))),
       repository = job$repository, commit = job$commit, entrypoint = "make inside-job"))
    list(descriptor = descriptor, software = list(container = effective$image, image_id = descriptor$image_id, R = "test-double"))
  },
  calculate = function(job, context, folder, runtime) {
    json_write(list(start = as.numeric(Sys.time())), file.path(folder, "test-start.json"))
    Sys.sleep(0.15)
    key <- job$key
    annual <- lapply(2021:2023, function(year) list(year = year, index = 1, catch_t = 100, observed_index = 1))
    result <- if (key == "submission") list(sets = rows, catch = catches) else if (key == "extract") context$extracted else
      if (key %in% c("cpue_a", "cpue_b")) list(series = annual) else if (key %in% c("assessment_a1", "assessment_a2", "assessment_b1", "assessment_b2")) list(K = 10000, r = 0.25, q = 0.01, next_biomass_t = 5000, series = annual) else list(job = key)
    json_write(list(end = as.numeric(Sys.time())), file.path(folder, "test-end.json"))
    list(result = result, effects = json_object())
  },
  render = function(job, result, record, folder, runtime, sources) {
    writeLines("<html>Runtime-double artifact</html>", file.path(folder, "report.html"))
    writeLines("%PDF-1.7 runtime-double artifact", file.path(folder, "report.pdf"))
    writeLines("Test-double report", file.path(folder, "report.qmd"))
    json_write(list(result = result, record = record), file.path(folder, "report-data.json"))
    list(quarto_executed = TRUE, runtime = runtime$descriptor, software = runtime$software,
         artifacts = as.list(c("report.html", "report.pdf", "report.qmd", "report-data.json")), test_double = TRUE)
  }
)
output <- file.path(fixture, "runs")
workflow <- new_workflow(output, runtime_backend = backend, handover = NULL, execution = list(max_workers = 2L))
stopifnot(length(workflow_plan(workflow)$run) == 22L)
run <- workflow_run(workflow)
stopifnot(length(run$run) == 22L, length(workflow$records) == 22L)
stopifnot(all(vapply(names(workflow$records), function(key) workflow_valid(workflow, key), logical(1))))
stopifnot(length(workflow_plan(workflow, "mse_buffered")$run) == 3L)
stopifnot(length(workflow_plan(workflow, "mse_buffered", "job")$run) == 1L)
failed_setting <- tryCatch({ workflow_configure(workflow, list(mse_buffer = 0.7)); FALSE }, error = function(error) TRUE)
stopifnot(failed_setting)
old_records <- lapply(workflow$records, json_encode)
workflow$handover <- function(boundary, group) {
  Sys.sleep(if (boundary == "cpue") 1 else 0.01)
  list(connected = FALSE, counter = (workflow$handover_state$counter %||% 0L) + 1L)
}
manual <- workflow_run(workflow)
stopifnot(workflow$handover_state$counter == 3L)
stopifnot(sum(vapply(workflow$events, function(event) event$state == "handover", logical(1))) == 3L)
report_event <- which(vapply(workflow$events, function(event) identical(event$job, "cpue_report") && event$state == "complete", logical(1)))
receipt_event <- which(vapply(workflow$events, function(event) identical(event$boundary, "cpue") && event$state == "received", logical(1)))
stopifnot(report_event < receipt_event)
workflow$handover <- NULL

# Two ready calculations must overlap when more than one worker is permitted.
start_a <- json_read(file.path(output, "cpue_a/test-start.json"))$start
end_a <- json_read(file.path(output, "cpue_a/test-end.json"))$end
start_b <- json_read(file.path(output, "cpue_b/test-start.json"))$start
end_b <- json_read(file.path(output, "cpue_b/test-end.json"))$end
stopifnot(max(start_a, start_b) < min(end_a, end_b))
# Restore a new-schema checkpoint without replacing its producer records.
restored <- new_workflow(output, runtime_backend = backend, handover = NULL)
stopifnot(identical(json_encode(restored$records), json_encode(workflow$records)))
archive <- file.path(fixture, "bundle.zip")
workflow_bundle(workflow, archive)
contents <- utils::unzip(archive, list = TRUE)$Name
stopifnot(all(c("source-lock.json", "source-origins.json", "runtime-catalogue.json", "runtime-overrides.json", "reference/state.json", "SHA256SUMS.json") %in% contents))
stopifnot(!any(startsWith(contents, "docs/")), !any(startsWith(contents, "app/")))
# A malformed response cannot create a successful record; successful peers survive resume.
broken_backend <- backend
broken_backend$calculate <- function(job, context, folder, runtime) {
  if (job$key == "cpue_a") return(list(result = list(index = NaN), effects = json_object()))
  backend$calculate(job, context, folder, runtime)
}
broken_output <- file.path(fixture, "failed-runs")
broken <- new_workflow(broken_output, runtime_backend = broken_backend, handover = NULL, execution = list(max_workers = 2L))
error <- tryCatch({ workflow_run(broken); NULL }, error = identity)
stopifnot(inherits(error, "error"), is.null(broken$records$cpue_a), !is.null(broken$records$cpue_b))
producer <- json_encode(broken$records$cpue_b)
resumed <- new_workflow(broken_output, runtime_backend = backend, handover = NULL, execution = list(max_workers = 2L))
invisible(workflow_run(resumed, "cpue_a"))
stopifnot(identical(json_encode(resumed$records$cpue_b), producer), length(resumed$records) == 22L)
base_origins <- origins; base_lock <- lock
for (key in c("mse_buffered", "assessment_a2", "cpue_a")) {
  origins <- base_origins; lock <- base_lock
  # Reset all binding files, then change only the selected effective image.
  for (group in names(source_groups)) {
    path <- file.path(fixture, "components", group, "runtime.json")
    json_write(list(schema_version = 1L, default = list(image = paste0("example/test@sha256:", strrep("1", 64L)), platform = "linux/amd64", package_url = ""), jobs = json_object()), path)
  }
  group <- source_group(key); path <- file.path(fixture, "components", group, "runtime.json")
  binding <- json_read(path); binding$jobs[[key]] <- list(image = paste0("example/test@sha256:", strrep("2", 64L))); json_write(binding, path)
  commit <- strrep("b", 40L); lock$repositories[[group]]$commit <- commit
  for (name in names(origins)[startsWith(names(origins), paste0("components/", group, "/"))]) origins[[name]]$commit <- commit
  origins[[paste0("components/", group, "/runtime.json")]]$sha256 <- file_sha256(path)
  json_write(lock, file.path(fixture, "source-lock.json")); json_write(list(schema_version = 1L, sources = origins), file.path(fixture, "source-origins.json"))
  changed <- new_workflow(output, runtime_backend = backend, handover = NULL, execution = list(max_workers = 2L))
  plan <- workflow_plan(changed, key)
  expected <- c(mse_buffered = 3L, assessment_a2 = 9L, cpue_a = 14L)[[key]]
  stopifnot(length(plan$run) == expected)
  retained <- unlist(plan$retained)
  stopifnot(all(vapply(retained, function(job) identical(json_encode(changed$records[[job]]), json_encode(workflow$records[[job]])), logical(1))))
}
# A wrong checksum fails closed before any new calculation.
cat("tamper", file = file.path(output, "cpue_b/output.json"))
stopifnot(!workflow_valid(changed, "cpue_b"))
cat("R workflow contract checks passed using explicit runtime doubles.\n")
unlink(fixture, recursive = TRUE)
