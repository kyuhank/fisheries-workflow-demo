#!/usr/bin/env Rscript
# Explicit hosted checks. POSTs are sent once; an uncertain write stays UNKNOWN.
live_assert <- function(ok, message) if (!isTRUE(ok)) stop(message, call. = FALSE)
live_equal <- function(a, b) identical(json_encode(a), json_encode(b))
live_unknown <- function(message) stop(structure(list(message = message, call = NULL),
  class = c("live_unknown", "error", "condition")))
live_save <- function(gate, value, name) {
  text <- json_encode(value)
  if (!is.null(gate$session) && nzchar(gate$session$token))
    live_assert(!grepl(gate$session$token, text, fixed = TRUE), "A capability was returned in public evidence")
  json_write(value, file.path(gate$evidence, name))
}
live_remaining <- function(gate) {
  remaining <- gate$deadline - gate$now()
  if (remaining < 1) live_unknown("Check deadline reached; inspect the existing request before another dispatch")
  remaining
}
live_request <- function(gate, path, body = NULL, reader = TRUE) {
  headers <- list("Content-Type" = "application/json")
  if (reader) {
    live_assert(!is.null(gate$session), "Supply a private reader session")
    path <- paste0(path, if (grepl("?", path, fixed = TRUE)) "&" else "?", "session=", gate$session$id)
    headers$Authorization <- paste("Bearer", gate$session$token)
  }
  payload <- if (is.null(body)) NULL else charToRaw(json_encode(body))
  for (attempt in seq_len(if (is.null(body)) 3L else 1L)) {
    timeout <- min(30, live_remaining(gate))
    response <- tryCatch(gate$http(paste0(gate$api, path), headers, payload, timeout = timeout), error = function(error) {
      if (!is.null(body)) live_unknown("POST connection interrupted; do not repeat this write")
      list(status = 0L, value = NULL)
    })
    code <- response$status
    if (!is.na(code) && code >= 200L && code < 300L && is.list(response$value)) return(response$value)
    if (!is.null(body)) live_unknown("POST response is uncertain; do not repeat this write")
    transient <- is.na(code) || code %in% c(0L, 408L, 429L, 500L, 502L, 503L, 504L) || (code >= 200L && code < 300L)
    if (!isTRUE(transient) || attempt == 3L) stop("Hosted GET failed (HTTP ", code, ")", call. = FALSE)
    gate$sleep(min(2^(attempt - 1L), live_remaining(gate)))
  }
}
live_github <- function(gate, path) {
  live_assert(grepl("^(commits/(main|[a-f0-9]{40})|actions/runs/[0-9]+)$", path), "Unsupported GitHub read")
  response <- gate$http(paste0("https://api.github.com/repos/", gate$repository, "/", path),
    list(Accept = "application/vnd.github+json", "User-Agent" = "fisheries-workflow-live-check"),
    timeout = min(30, live_remaining(gate)))
  live_assert(identical(as.integer(response$status), 200L) && is.list(response$value), "Public GitHub verification GET failed")
  gate$github_reads <- gate$github_reads + 1L
  live_save(gate, response$value, sprintf("github-%03d.json", gate$github_reads))
  response$value
}
live_session <- function(path) {
  live_assert(file.exists(path) && !dir.exists(path) && !nzchar(Sys.readlink(path)), "Missing regular reader-session file")
  live_assert(as.integer(file.info(path)$mode) == strtoi("600", base = 8L), "Reader-session file must have mode0600")
  session <- json_read(path)
  live_assert(setequal(names(session), c("id", "token")) &&
    grepl("^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$", session$id %||% "") &&
    is.character(session$token) && length(session$token) == 1L && nzchar(session$token), "Invalid private reader session")
  session
}
live_private_path <- function(path) {
  path <- path.expand(path)
  if (!startsWith(path, "/")) path <- file.path(getwd(), path)
  parent <- dirname(path); suffix <- basename(path)
  while (!dir.exists(parent)) { suffix <- file.path(basename(parent), suffix); parent <- dirname(parent) }
  source_path(normalizePath(parent, mustWork = TRUE), suffix, exists = FALSE)
}
live_create <- function(gate, path) {
  marker <- file.path(gate$evidence, "session.started.json")
  live_assert(!file.exists(marker) && !file.exists(path), "Session creation already has custody; use its existing private file")
  live_save(gate, list(status = "UNKNOWN", action = "create_reader", started_utc = format(Sys.time(), tz = "UTC", usetz = TRUE)), "session.started.json")
  session <- live_request(gate, "/session", list(), reader = FALSE)
  if (!setequal(names(session), c("id", "token"))) live_unknown("Session response was invalid; do not repeat creation")
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE, mode = "0700")
  link <- Sys.readlink(path)
  live_assert(is.na(link) || !nzchar(link), "Reader-session destination is a symlink")
  json_write(session, path); Sys.chmod(path, "0600")
  gate$session <- live_session(path)
  live_save(gate, list(status = "created", private_session_file = path), "session.receipt.json")
}
live_case <- function(name, config, previous = NULL, connect = FALSE) {
  jobs <- config$jobs; keys <- names(jobs); fresh <- name %in% c("baseline", "jobscope")
  records <- previous$records %||% list()
  live_assert(if (fresh) !length(records) else identical(previous$schema_version, 2L) && setequal(names(records), keys),
    "This case requires a fresh reader or a complete schema2 baseline, respectively")
  settings <- if (fresh) utils::modifyList(config$defaults, list(last_year = 2021L, mse = TRUE)) else previous$settings
  start <- "submission"; scope <- "workflow"; handover <- "connected"
  if (name == "growthupdate") { settings$growth_rate_2 <- if (settings$growth_rate_2 == .35) .30 else .35; start <- "assessment_report"; handover <- "manual" }
  if (name == "msebuffer") { settings$mse_buffer <- if (settings$mse_buffer == .6) .8 else .6; start <- "mse_report" }
  if (name == "cpue-update") { settings$min_hooks_a <- if (settings$min_hooks_a == 0) 1200 else 0; start <- "cpue_a"; handover <- "manual" }
  if (name == "jobscope") { start <- "cpue_a"; scope <- "job" }
  live_assert(name %in% c("baseline", "growthupdate", "msebuffer", "cpue-update", "jobscope"), "Unknown Live case")
  changed <- if (fresh) keys else keys[!vapply(keys, function(key)
    live_equal(workflow_job_settings(list(settings = settings), key), workflow_job_settings(list(settings = previous$settings), key)), logical(1))]
  selected <- workflow_downstream(c(start, changed), jobs)
  if (scope == "job") {
    required <- character()
    include <- function(key) { required <<- union(required, key); for (parent in unlist(jobs[[key]]$parents)) include(parent) }
    include(start); selected <- keys[keys %in% required]
  }
  boundaries <- list()
  if (handover == "manual") for (stage in config$stages) {
    group <- intersect(unlist(stage), selected)
    if (length(group)) boundaries <- c(boundaries, workflow_handovers(list(config = config), group, selected))
  }
  if (connect && length(boundaries)) boundaries <- boundaries[1L]
  list(name = name, body = list(start = start, settings = settings, handover = handover, scope = scope),
    run = as.list(selected), retained = as.list(keys[keys %in% setdiff(names(records), selected)]), boundaries = boundaries, connect = connect)
}
live_events <- function(events, selected, config) {
  at <- function(key, state) which(vapply(events, function(event) identical(event$job, key) && identical(event$state, state), logical(1)))
  observed <- function(state) unique(vapply(Filter(function(event) identical(event$state, state), events), function(event) event$job %||% "", character(1)))
  live_assert(setequal(observed("running"), selected) && setequal(observed("complete"), selected), "Executed event jobs differ from the expected graph")
  for (key in selected) {
    running <- at(key, "running"); completed <- at(key, "complete")
    live_assert(length(running) && length(completed) && min(running) < min(completed) && max(running) < max(completed), paste("Invalid event order:", key))
    if (!key %in% c("submission", "qc")) live_assert(length(running) == 1L && length(completed) == 1L, paste("Repeated job:", key))
  }
  for (stage in config$stages) {
    peers <- intersect(unlist(stage), selected)
    if (!length(peers)) next
    for (key in selected) if (any(unlist(config$jobs[[key]]$parents) %in% peers)) {
      if (key == "qc" && identical(peers, "submission")) {
        live_assert(min(at("submission", "complete")) < min(at(key, "running")), "Initial QC barrier failed")
        live_assert(max(at("submission", "complete")) < max(at(key, "running")), "Corrected QC barrier failed")
      } else live_assert(max(unlist(lapply(peers, at, state = "complete"))) < min(at(key, "running")), paste("Peer barrier failed:", key))
    }
  }
}
live_transfer <- function(gate, pending, run, events, case, confirmed, previous) {
  index <- length(confirmed) + 1L
  live_assert(index <= length(case$boundaries), "Unexpected manual boundary")
  expected <- case$boundaries[[index]]
  live_assert(identical(pending$boundary, expected$boundary) && live_equal(pending$group, expected$group) &&
    identical(pending$request_id, run$id) && is.numeric(pending$transfer_count) && length(pending$transfer_count) == 1L &&
    pending$transfer_count == index - 1L, "Transfer recipients, identity or counter differ")
  report <- switch(pending$boundary, cpue = "cpue_report", assessment = "assessment_report", NULL)
  complete <- vapply(Filter(function(event) identical(event$state, "complete"), events), function(event) event$job, character(1))
  if (!is.null(report) && !report %in% complete) return(FALSE)
  live_assert(!any(vapply(events, function(event) identical(event$state, "running") && event$job %in% unlist(pending$group), logical(1))), "A recipient started before file transfer")
  if (!identical(run$status, "handover")) return(FALSE)
  for (key in intersect(unlist(pending$group), names(previous$records))) {
    old <- live_request(gate, paste0("/output?job=", key))
    live_assert(live_equal(old$record, previous$records[[key]]), "A preserved result changed before transfer")
    live_save(gate, old, paste0("before-transfer-", key, ".json"))
  }
  marker <- paste0("transfer-", index, ".started.json")
  live_assert(!file.exists(file.path(gate$evidence, marker)), "This acknowledgement was already attempted; inspect its receipt")
  body <- list(connect = case$connect, request_id = pending$request_id, transfer_count = pending$transfer_count)
  live_save(gate, list(status = "UNKNOWN", body = body, report_completed = report), marker)
  receipt <- live_request(gate, "/transfer", body)
  live_assert(isTRUE(receipt$ok) && identical(receipt$request_id, run$id) && receipt$transfer_count == pending$transfer_count + 1L &&
    identical(receipt$connected, case$connect), "Transfer receipt differs")
  live_save(gate, receipt, paste0("transfer-", index, ".receipt.json")); TRUE
}
live_identity <- function(gate, run_id, commit) {
  live_assert(grepl("^[0-9]{1,20}$", run_id) && identical(commit, gate$commit), "Unexpected producing GitHub identity")
  if (run_id %in% gate$verified_runs) return(invisible(NULL))
  repeat {
    remote <- live_github(gate, paste0("actions/runs/", run_id))
    live_assert(identical(remote$repository$full_name, gate$repository) && identical(remote$head_sha, commit) &&
      identical(remote$head_branch, "main") && identical(remote$event, "workflow_dispatch") &&
      identical(remote$path, ".github/workflows/live.yml"), "Public GitHub execution identity differs")
    if (identical(run_id, gate$current_github_run)) {
      created <- as.numeric(as.POSIXct(remote$created_at, format = "%Y-%m-%dT%H:%M:%OSZ", tz = "UTC"))
      live_assert(grepl(gate$request_id, remote$display_title %||% "", fixed = TRUE) &&
        is.finite(created) && created >= gate$dispatch_time - 10, "GitHub run is not the fresh registered dispatch")
    }
    if (identical(remote$status, "completed")) { live_assert(identical(remote$conclusion, "success"), "GitHub workflow did not succeed"); break }
    gate$sleep(min(3, live_remaining(gate)))
  }
  gate$verified_runs <- c(gate$verified_runs, run_id)
}
live_record <- function(gate, key, record, records) {
  origin <- source_origin(gate$sources, key)
  live_assert(identical(record$schema_version, 2L) && identical(record$job, key) && live_equal(record$analysis_source, origin), paste("Component source differs:", key))
  live_assert(live_equal(record$source, list(repository = paste0("https://github.com/", gate$repository), commit = gate$commit)), "Coordinator source differs")
  code <- source_code(gate$sources, key, hosted = TRUE)
  live_assert(live_equal(record$code, code), paste("Loaded source bytes differ:", key))
  origins <- source_code_origins(gate$sources, key)
  for (name in setdiff(names(code), names(origins))) origins[[name]] <- list(repository = paste0("https://github.com/", gate$repository), commit = gate$commit, path = name, sha256 = code[[name]])
  live_assert(live_equal(record$code_sources, origins), paste("Source origin pins differ:", key))
  binding <- runtime_binding(list(key = key), gate$sources)$entry
  identity <- record$runtime; software <- record$software; rendering <- record$report_rendering
  live_assert(identical(identity$image, binding$image) && identical(identity$platform, binding$platform) &&
    grepl("^sha256:[a-f0-9]{64}$", identity$image_id %||% "") && length(identity$rootfs_diff_ids) > 0L &&
    all(grepl("^sha256:[a-f0-9]{64}$", unlist(identity$rootfs_diff_ids))), paste("Calculation image differs:", key))
  for (field in c("image_id", "platform", "rootfs_diff_ids")) live_assert(live_equal(software[[field]], identity[[field]]), "Observed software image differs")
  live_assert(identical(software$container, identity$image) && is.character(software$r) && nzchar(software$r) &&
    is.character(software$quarto) && nzchar(software$quarto) && length(software$packages) &&
    all(vapply(software$packages, function(version) is.character(version) && length(version) == 1L && nzchar(version), logical(1))), "Missing actual R/Quarto/package versions")
  if (grepl("^assessment_[ab][12]$", key)) live_assert(all(c("RTMB", "TMB") %in% names(software$packages)), "Assessment native package identities missing")
  live_assert(isTRUE(rendering$quarto_executed) && is.character(rendering$version) && nzchar(rendering$version), "Actual Quarto renderer is missing")
  for (field in names(identity)) live_assert(live_equal(rendering$runtime[[field]], identity[[field]]), "Actual Quarto renderer identity differs")
  execution <- record$execution
  live_assert(isTRUE(execution$hosted) && identical(execution$provider, "GitHub Actions") && identical(execution$repository, gate$repository) &&
    identical(execution$container, identity$image) && identical(execution$image_id, identity$image_id), "Hosted record provider/image differs")
  live_assert(is.character(execution$coordinator$R) && all(c("jsonlite", "digest", "DBI", "RSQLite") %in% names(execution$coordinator$packages)), "Host coordinator software identity is missing")
  live_identity(gate, as.character(execution$github_run), execution$commit)
  for (parent in unlist(gate$config$jobs[[key]]$parents)) {
    input <- record$inputs[[parent]]; producer <- records[[parent]]
    live_assert(!is.null(producer) && identical(input$run_id, producer$run_id) && identical(input$checksum, producer$outputs[["output.json"]]) &&
      identical(input$signature, producer$signature) && live_equal(input$analysis_source, producer$analysis_source), paste("Producing input differs:", key, parent))
  }
}
live_bundle <- function(gate, request, value) {
  publication <- live_request(gate, "/bundle")
  live_assert(identical(publication$request_id, request), "Bundle belongs to another request")
  bytes <- cloud_base64(publication$bundle)
  archive <- file.path(gate$evidence, "bundle.zip"); writeBin(bytes, archive)
  members <- utils::unzip(archive, list = TRUE)
  live_assert(nrow(members) > 0L && nrow(members) <= 2000L && sum(members$Length) <= 64000000, "Bundle member/size limit exceeded")
  directory <- file.path(gate$evidence, "bundle"); dir.create(directory)
  cloud_restore(publication$bundle, directory); manifest <- release_manifest(directory, exact = TRUE)
  for (group in names(gate$sources$files)) for (name in names(gate$sources$files[[group]]))
    live_assert(identical(manifest[[paste0("components/", group, "/", name)]], gate$sources$files[[group]][[name]]), "Archived component closure differs from its pinned source")
  live_assert(live_equal(json_read(file.path(directory, "reference/state.json"))$records, value$records), "Bundle records differ from the published result")
  live_assert(live_equal(json_read(file.path(directory, "settings.json")), value$settings), "Bundle settings differ")
  if (!is.null(value$records$submission)) live_assert(identical(manifest[["data/frozen-source.json"]], value$records$submission$execution$data_checksum), "Frozen source differs from the actual hosted input")
  catalogue <- json_read(file.path(directory, "runtime-catalogue.json"))$images
  image_ids <- character()
  for (key in names(value$records)) {
    record <- value$records[[key]]; folder <- file.path(directory, "reference", key)
    for (name in names(record$outputs)) live_assert(identical(manifest[[paste0("reference/", key, "/", name)]], record$outputs[[name]]), "Bundle output checksum differs")
    for (name in names(record$code)) live_assert(identical(manifest[[name]], record$code[[name]]), "Bundle source checksum differs")
    for (target in c("inside-job", "render")) {
      receipt <- json_read(file.path(folder, paste0("container-", target, ".json")))
      live_assert(identical(receipt$job, key) && identical(receipt$target, target) && identical(receipt$image_id, record$runtime$image_id) &&
        identical(receipt$image, record$runtime$image) && live_equal(receipt$rootfs_diff_ids, record$runtime$rootfs_diff_ids) &&
        identical(receipt$platform, record$runtime$platform) && grepl("^[a-f0-9]{64}$", receipt$container_id %||% "") &&
        live_equal(receipt$command, list("make", target, paste0("JOB=", key))) && identical(as.integer(receipt$docker_status), 0L) &&
        identical(as.integer(receipt$exit_code), 0L) && !isTRUE(receipt$running), "Actual Make container receipt differs")
      if (target == "render") live_assert(live_equal(receipt, record$report_rendering$container), "Saved renderer receipt differs from its record")
    }
    live_assert(identical(rawToChar(cloud_bytes(file.path(folder, "report.pdf"))[1:5]), "%PDF-"), "Invalid saved PDF")
    public <- live_request(gate, paste0("/output?job=", key))
    live_assert(live_equal(public$record, record) && live_equal(public$output, json_read(file.path(folder, "output.json"))) &&
      identical(digest::digest(cloud_base64(public$pdf_base64), algo = "sha256", serialize = FALSE), record$outputs[["report.pdf"]]) &&
      identical(sub("\n+$", "", public$html), sub("\n+$", "", paste(readLines(file.path(folder, "report.html"), warn = FALSE), collapse = "\n"))), "Public numerical/report output differs from its saved bundle")
    live_save(gate, public, paste0("output-", key, ".json"))
    found <- Filter(function(image) identical(image$image, record$runtime$image) && identical(image$image_id, record$runtime$image_id) &&
      identical(image$platform, record$runtime$platform) && live_equal(image$rootfs_diff_ids, record$runtime$rootfs_diff_ids), catalogue)
    live_assert(length(found) == 1L, "Runtime catalogue does not identify the producer/renderer")
    for (role in c("calculation", "rendering")) live_assert(any(vapply(found[[1L]]$uses, function(use)
      identical(use$job, key) && identical(use$role, role) && identical(use$run_id, record$run_id), logical(1))), "Runtime catalogue use differs")
    image_ids <- union(image_ids, record$runtime$image_id)
  }
  if (length(value$records) == length(gate$config$jobs)) live_assert(length(image_ids) >= 2L, "Full hosted workflow did not use distinct image configurations")
  list(sha256 = file_sha256(archive), files = length(manifest), image_config_ids = as.list(image_ids), reproduction = "separate gate")
}
live_execute <- function(gate, case, previous) {
  live_assert(!file.exists(file.path(gate$evidence, "dispatch.started.json")), "This dispatch has existing custody; inspect it without dispatching again")
  gate$dispatch_time <- gate$now()
  live_save(gate, list(status = "UNKNOWN", expected_commit = gate$commit, case = case, started_utc = format(Sys.time(), tz = "UTC", usetz = TRUE)), "dispatch.started.json")
  dispatched <- live_request(gate, "/run", case$body)
  if (!grepl("^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$", dispatched$id %||% "")) live_unknown("Dispatch response lacks an identity; do not dispatch again")
  gate$request_id <- dispatched$id; live_save(gate, dispatched, "dispatch.receipt.json")
  cursor <- 0; events <- list(); confirmed <- character(); pending <- NULL; reads <- 0L
  repeat {
    update <- live_request(gate, paste0("/state?after=", format(cursor, scientific = FALSE)))
    reads <- reads + 1L; live_save(gate, update, sprintf("state-%04d.json", reads))
    run <- update$run
    live_assert(identical(run$id, gate$request_id) && identical(run$commit_sha, gate$commit), "State request/source identity differs")
    for (row in update$events) {
      live_assert(is.numeric(row$id) && length(row$id) == 1L && row$id > cursor && identical(row$request_id, run$id), "Events are unordered or belong to another request")
      cursor <- row$id; events[[length(events) + 1L]] <- row$event
      if (identical(row$event$state, "handover")) { live_assert(is.null(pending), "Overlapping manual transfers"); pending <- row$event }
    }
    if (run$status %in% c("failed", "expired")) stop("Hosted request ended: ", run$status, call. = FALSE)
    if (!is.null(pending) && live_transfer(gate, pending, run, events, case, confirmed, previous)) {
      confirmed <- c(confirmed, pending$boundary); pending <- NULL
    }
    if (identical(run$status, "complete") && length(update$events) < 100L) {
      live_assert(is.null(pending), "Request completed with an unacknowledged boundary")
      value <- run$result
      if (is.null(value$records)) value$records <- update$state$records
      live_assert(is.list(value$records), "Completed run has no producing records")
      live_assert(identical(value$schema_version, 2L) && live_equal(value$run, case$run) && live_equal(value$retained, case$retained) &&
        identical(value$start, case$body$start) && identical(value$scope, case$body$scope) && live_equal(value$settings, case$body$settings), "Completed plan/settings differ")
      plans <- Filter(function(event) identical(event$state, "plan"), events)
      live_assert(length(plans) == 1L && live_equal(plans[[1L]]$run, case$run) && live_equal(plans[[1L]]$retained, case$retained), "Published event plan differs")
      received <- vapply(Filter(function(event) identical(event$state, "received"), events), function(event) event$boundary, character(1))
      expected <- vapply(case$boundaries, function(boundary) boundary$boundary, character(1))
      live_assert(identical(confirmed, expected) && identical(received, expected), "Manual boundaries differ")
      live_events(events, unlist(case$run), gate$config)
      gate$current_github_run <- as.character(run$github_run)
      live_identity(gate, as.character(run$github_run), run$commit_sha)
      live_assert(identical(live_github(gate, "commits/main")$sha, gate$commit), "Public main changed during this check")
      for (key in unlist(case$retained)) live_assert(live_equal(value$records[[key]], previous$records[[key]]), paste("Retained producing record changed:", key))
      for (key in names(value$records)) {
        if (key %in% unlist(case$run)) live_assert(identical(value$records[[key]]$run_id, value$run_id), "Current analysis run identity differs")
        live_record(gate, key, value$records[[key]], value$records)
      }
      live_save(gate, events, "events.json"); live_save(gate, value, "result.json")
      return(list(request_id = run$id, github_run = as.character(run$github_run), run = value$run, retained = value$retained,
        boundaries = as.list(confirmed), bundle = live_bundle(gate, run$id, value)))
    }
    gate$sleep(min(if (length(update$events) == 100L) .1 else 2, live_remaining(gate)))
  }
}
live_main <- function(args = commandArgs(TRUE)) {
  script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
  root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
  for (name in c("sources", "inputs", "workflow", "runtime", "cloud")) source(file.path(root, "R", paste0(name, ".R")))
  source(file.path(root, "scripts/release.R")); workflow_require(c("jsonlite", "digest"))
  options <- list(mode = "preflight", case = NULL, evidence = NULL, expected_commit = NULL, session_file = NULL, timeout = "600", connect = FALSE)
  while (length(args)) {
    key <- gsub("-", "_", sub("^--", "", args[[1L]]))
    if (identical(key, "connect")) { options$connect <- TRUE; args <- args[-1L]; next }
    live_assert(startsWith(args[[1L]], "--") && key %in% names(options) && length(args) >= 2L, "Use --mode preflight|create|execute --case CASE --evidence DIR --expected-commit SHA [--session-file PATH] [--connect]")
    options[[key]] <- args[[2L]]; args <- args[-c(1L, 2L)]
  }
  live_assert(options$mode %in% c("preflight", "create", "execute") && options$case %in% c("baseline", "growthupdate", "msebuffer", "cpue-update", "jobscope") &&
    !is.null(options$evidence) && grepl("^[a-f0-9]{40}$", options$expected_commit %||% ""), "Specify mode, case, evidence and exact expected commit")
  timeout <- suppressWarnings(as.numeric(options$timeout)); live_assert(length(timeout) == 1L && is.finite(timeout) && timeout > 0 && timeout <= 600, "Timeout must be at most600 seconds")
  dir.create(options$evidence, recursive = TRUE, showWarnings = FALSE)
  gate <- new.env(parent = emptyenv()); gate$evidence <- normalizePath(options$evidence, mustWork = TRUE)
  gate$root <- root; gate$commit <- options$expected_commit; gate$http <- cloud_http; gate$now <- function() as.numeric(Sys.time()); gate$sleep <- Sys.sleep
  gate$deadline <- gate$now() + timeout; gate$session <- NULL; gate$github_reads <- 0L; gate$verified_runs <- character(); gate$request_id <- NULL
  config <- json_read(file.path(root, "cloud/config.json")); gate$api <- config$url; gate$repository <- config$repository
  gate$config <- workflow_spec(root); gate$sources <- new_sources(root)
  live_assert(identical(config$repository, "kyuhank/fisheries-workflow-demo") && startsWith(gate$api, "https://"), "Unexpected hosted service")
  report <- list(schema_version = 1L, status = "failed", mode = options$mode, case = options$case, expected_commit = gate$commit)
  on.exit(live_save(gate, report, "report.json"), add = TRUE)
  tryCatch({
    live_assert(identical(source_git(root, c("rev-parse", "HEAD")), gate$commit), "Local checkout is not the expected commit")
    source_verify(gate$sources)
    live_assert(identical(source_coordinator(gate$sources)$commit, gate$commit), "Hydrate the committed coordinator before checking Live")
    files <- c("scripts/check-live.R", "R/cloud.R", "R/sources.R", "R/inputs.R", "R/workflow.R", "R/runtime.R", "scripts/release.R", "workflow/jobs.json", "source-lock.json")
    live_save(gate, list(expected_commit = gate$commit, source_sha256 = setNames(lapply(file.path(root, files), file_sha256), files),
      component_pins = lapply(gate$sources$repositories, function(repo) repo[c("repository", "commit")])), "sources.json")
    info <- live_request(gate, "/info", reader = FALSE); live_save(gate, info, "service-info.json")
    live_assert(isTRUE(info$configured) && identical(info$repository, gate$repository) && identical(info$data_kind, config$data_kind) && identical(info$source_sha256, config$source_sha256), "Service preparation/source identity differs")
    live_assert(identical(live_github(gate, "commits/main")$sha, gate$commit), "Public main differs from the expected commit")
    session_path <- options$session_file %||% file.path(path.expand("~/.local/state/fisheries-workflow"), paste0("reader-", options$expected_commit, ".json"))
    session_path <- live_private_path(session_path)
    for (public in c(gate$evidence, file.path(root, "docs"), file.path(root, "dist")))
      live_assert(!identical(session_path, public) && !startsWith(session_path, paste0(public, "/")), "Keep the private session file outside public evidence/output directories")
    if (options$mode == "create") {
      live_create(gate, session_path); report$status <- "created"; report$private_session_file <- session_path
    } else {
      if (file.exists(session_path)) gate$session <- live_session(session_path)
      previous <- NULL
      if (!is.null(gate$session)) {
        before <- live_request(gate, "/state?after=0"); live_save(gate, before, "before.json")
        live_assert(is.null(before$run) || !before$run$status %in% c("queued", "running", "handover"), "Reader already has an active request")
        previous <- before$state
      }
      case <- live_case(options$case, gate$config, previous, options$connect); live_save(gate, case, "case.json")
      report$expected_jobs <- length(case$run); report$expected_boundaries <- case$boundaries
      if (options$mode == "execute") {
        live_assert(!is.null(gate$session), "Create a private reader first, then execute with its session file")
        report$execution <- live_execute(gate, case, previous); report$status <- "passed"
      } else report$status <- "preflight_passed"
    }
  }, error = function(error) {
    report$status <<- if (inherits(error, "live_unknown")) "UNKNOWN" else "failed"
    report$error <<- conditionMessage(error); report$request_id <<- gate$request_id
  })
  cat(report$status, options$case, "\n")
  invisible(report)
}
if (sys.nframe() == 0L) {
  result <- live_main()
  if (!result$status %in% c("passed", "preflight_passed", "created")) quit(status = 1L)
}
