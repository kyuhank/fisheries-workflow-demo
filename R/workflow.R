# R coordinates files and dependencies; each component runs its own Make targets.
# Host packages: jsonlite, digest, DBI, RSQLite. Parallel workers use base parallel.
workflow_spec <- function(root) {
  config <- json_read(file.path(root, "workflow/jobs.json"))
  if (!setequal(names(config), c("jobs", "defaults", "stages", "handovers"))) stop("Invalid workflow declaration")
  seen <- character(); fields <- c("key", "title", "module", "owner", "parents", "run", "description")
  for (job in config$jobs) {
    parents <- unlist(job$parents, use.names = FALSE)
    if (!setequal(names(job), fields) || !grepl("^[a-z][a-z0-9_]*$", job$key) || job$key %in% seen ||
        anyDuplicated(parents) || !all(parents %in% seen) || !identical(job$run, paste0("jobs/", job$key, "/run.R"))) stop("Invalid job declaration: ", job$key)
    if (!all(vapply(job[c("title", "module", "owner", "description")], function(x) is.character(x) && length(x) == 1L && nzchar(trimws(x)), logical(1)))) stop("Incomplete job description: ", job$key)
    seen <- c(seen, job$key)
  }
  flattened <- unlist(config$stages, use.names = FALSE)
  if (!all(lengths(config$stages) > 0L) || anyDuplicated(flattened) || !setequal(flattened, seen)) stop("Each job must appear in one stage")
  jobs <- setNames(config$jobs, seen); position <- setNames(rep(seq_along(config$stages), lengths(config$stages)), flattened)
  for (job in jobs) if (any(position[unlist(job$parents)] >= position[[job$key]])) stop("Parents must precede their child stage")
  for (boundary in config$handovers) for (key in names(boundary)) {
    parents <- unlist(boundary[[key]], use.names = FALSE)
    if (!key %in% seen || !length(parents) || anyDuplicated(parents) || !all(parents %in% unlist(jobs[[key]]$parents))) stop("Invalid file transfer boundary")
  }
  config$jobs <- jobs; config
}
workflow_jobs <- function(workflow) Filter(function(job) isTRUE(workflow$settings$mse) || job$module != "mse", workflow$config$jobs)
workflow_backend <- function(workflow, operation, ...) {
  fun <- workflow$runtime_backend[[operation]]
  if (is.null(fun)) fun <- get(paste0("runtime_", operation), mode = "function")
  fun(...)
}
workflow_runtime <- function(workflow, key) {
  if (is.null(workflow$runtimes[[key]])) {
    job <- c(workflow$config$jobs[[key]], source_job(workflow$sources, key)[c("group", "root", "repository", "commit")])
    workflow_event(workflow, key, "activity", "Checking the assigned container and software.", activity = "preparing", title = "Preparing job software")
    runtime <- workflow_backend(workflow, "prepare", job, workflow$sources, workflow$output)
    if (!is.list(runtime) || !is.list(runtime$software)) stop("Runtime preparation must return descriptor and actual software: ", key)
    workflow$runtimes[[key]] <- runtime
  }
  workflow$runtimes[[key]]
}
workflow_runtime_material <- function(runtime) {
  descriptor <- runtime$descriptor %||% runtime
  fields <- c("image", "image_id", "platform", "rootfs_diff_ids", "package_url", "entrypoint")
  list(descriptor = descriptor[intersect(fields, names(descriptor))], software = runtime$software)
}
workflow_host_software <- function() list(r = as.character(getRversion()), platform = R.version$platform,
  packages = lapply(setNames(c("jsonlite", "digest", "DBI", "RSQLite"), c("jsonlite", "digest", "DBI", "RSQLite")),
    function(package) as.character(utils::packageVersion(package))))
workflow_job_settings <- function(workflow, key) {
  switch(key,
    submission = list(last_year = workflow$settings$last_year),
    cpue_a = list(min_hooks = workflow$settings$min_hooks_a),
    assessment_a1 = list(r = 0.25), assessment_b1 = list(r = 0.25),
    assessment_a2 = list(r = workflow$settings$growth_rate_2), assessment_b2 = list(r = workflow$settings$growth_rate_2),
    mse_buffered = list(buffer = workflow$settings$mse_buffer), json_object())
}
workflow_signature <- function(workflow, key) {
  parents <- lapply(unlist(workflow$config$jobs[[key]]$parents), function(parent) {
    record <- workflow$records[[parent]]
    list(signature = record$signature, outputs = record$outputs)
  })
  names(parents) <- unlist(workflow$config$jobs[[key]]$parents)
  if (!length(parents)) parents <- json_object()
  material <- list(schema_version = 2L, encoding = "sorted-json-r-v1", code = source_code(workflow$sources, key, workflow$execution$hosted, workflow$execution$local),
                   settings = workflow_job_settings(workflow, key), parents = parents,
                   runtime = workflow_runtime_material(workflow_runtime(workflow, key)), coordinator_software = workflow_host_software())
  if (key == "submission") material$data <- input_files(workflow)
  value_sha256(material)
}
workflow_valid <- function(workflow, key) {
  record <- workflow$records[[key]]
  if (is.null(record) || !identical(record$signature, workflow_signature(workflow, key))) return(FALSE)
  if (is.null(record$report_rendering) || !isTRUE(record$report_rendering$quarto_executed) ||
      !all(c("output.json", "report.html", "report.pdf") %in% names(record$outputs))) return(FALSE)
  expected <- source_origin(workflow$sources, key)
  if (!all(vapply(c("repository", "path", "sha256"), function(field) identical(record$analysis_source[[field]], expected[[field]]), logical(1))) ||
      !grepl("^[a-f0-9]{40}$", record$analysis_source$commit %||% "")) return(FALSE)
  all(vapply(names(record$outputs), function(name) {
    path <- source_path(file.path(workflow$output, key), name, exists = FALSE)
    file.exists(path) && identical(file_sha256(path), record$outputs[[name]])
  }, logical(1)))
}
new_workflow <- function(output, settings = list(), notify = function(event, state, output = NULL) {},
                         handover = function(boundary, group) {}, execution = list(),
                         runtime_backend = NULL, source_lock = "source-lock.json") {
  workflow_require()
  workflow <- new.env(parent = emptyenv())
  workflow$root <- normalizePath(getOption("workflow.root", getwd()), mustWork = TRUE)
  dir.create(output, recursive = TRUE, showWarnings = FALSE)
  workflow$output <- normalizePath(output, mustWork = TRUE)
  workflow$config <- workflow_spec(workflow$root)
  workflow$sources <- new_sources(workflow$root, source_lock)
  workflow$settings <- workflow$config$defaults
  if (!identical(Sys.getenv("PAPER_DATA_MODE"), "synthetic")) workflow$settings$last_year <- 2021L
  workflow$notify <- notify; workflow$handover <- handover; workflow$execution <- execution
  workflow$runtime_backend <- runtime_backend %||% list(); workflow$runtimes <- list()
  workflow$records <- json_object(); workflow$events <- list(); workflow$run_number <- 0L
  workflow$last_plan <- NULL; workflow$running <- FALSE; workflow$handover_state <- NULL
  saved <- file.path(workflow$output, "state.json")
  if (file.exists(saved)) {
    previous <- json_read(saved)
    if (!identical(previous$schema_version, 2L)) stop("This checkpoint predates the R workflow schema. Preserve its bundle and use a new output directory.")
    workflow$settings <- utils::modifyList(workflow$settings, previous$settings)
    workflow$records <- previous$records; workflow$run_number <- previous$run_number
    workflow$last_plan <- previous$last_plan; workflow$handover_state <- previous$handover_state
  }
  workflow_configure(workflow, settings)
  workflow
}
workflow_configure <- function(workflow, settings) {
  candidate <- utils::modifyList(workflow$settings, settings)
  member <- function(value, choices) is.numeric(value) && length(value) == 1L && is.finite(value) && value %in% choices
  if (!setequal(names(candidate), names(workflow$config$defaults))) stop("Unknown analysis setting")
  if (!member(candidate$last_year, 2021:2024)) stop("Select a supplied data snapshot")
  if (!member(candidate$min_hooks_a, c(0, 1200))) stop("Select a supplied CPUE filter")
  if (!member(candidate$growth_rate_2, c(0.25, 0.30, 0.35))) stop("Select a supplied growth setting")
  if (!is.logical(candidate$mse) || length(candidate$mse) != 1L || is.na(candidate$mse)) stop("Select whether to include MSE")
  if (!member(candidate$mse_buffer, c(0.6, 0.8, 1))) stop("Select a supplied MSE catch buffer")
  source <- input_source(workflow)
  if (input_public(source)) {
    years <- intersect(vapply(source$sets, function(row) row$year, numeric(1)), vapply(source$catch, function(row) row$year, numeric(1)))
    if (!candidate$last_year %in% c(2021, 2022) || !candidate$last_year %in% years) stop("The public-data example supplies the 2021 and 2022 snapshots")
  }
  workflow$settings <- candidate
  invisible(workflow)
}
workflow_downstream <- function(roots, jobs) {
  selected <- roots
  for (key in names(jobs)) if (any(unlist(jobs[[key]]$parents) %in% selected)) selected <- union(selected, key)
  names(jobs)[names(jobs) %in% selected]
}
workflow_plan <- function(workflow, start = "submission", scope = "workflow") {
  source_verify(workflow$sources)
  jobs <- workflow_jobs(workflow)
  if (!start %in% names(jobs)) stop("Unknown starting job")
  if (!scope %in% c("job", "workflow")) stop("Select job or workflow execution")
  changed <- names(jobs)[!vapply(names(jobs), function(key) workflow_valid(workflow, key), logical(1))]
  if (scope == "workflow") selected <- workflow_downstream(c(start, changed), jobs)
  else {
    required <- character()
    include <- function(key) {
      if (key %in% required) return(invisible(NULL))
      required <<- c(required, key)
      for (parent in unlist(jobs[[key]]$parents)) include(parent)
    }
    include(start); selected <- character()
    for (key in names(jobs)) if (key %in% required && (key == start || key %in% changed || any(unlist(jobs[[key]]$parents) %in% selected))) selected <- c(selected, key)
  }
  list(run = as.list(selected), retained = as.list(setdiff(intersect(names(jobs), names(workflow$records)), selected)),
       changed = as.list(changed), start = start, scope = scope)
}
workflow_state <- function(workflow) {
  list(schema_version = 2L, settings = workflow$settings, records = workflow$records, run_number = workflow$run_number,
       last_plan = workflow$last_plan, jobs = unname(workflow_jobs(workflow)), events = workflow$events,
       handover_state = workflow$handover_state)
}
workflow_persist <- function(workflow) json_write(workflow_state(workflow), file.path(workflow$output, "state.json"))
workflow_event <- function(workflow, key, state, message, ...) {
  event <- c(list(job = key, state = state, message = message), list(...))
  workflow$events[[length(workflow$events) + 1L]] <- event
  workflow$notify(c(event, list(record = workflow$records[[key]])), workflow_state(workflow), workflow$output)
  invisible(event)
}
workflow_output <- function(workflow, key) {
  if (!workflow_valid(workflow, key)) stop("Transfer input stale or checksum mismatch: ", key)
  path <- file.path(workflow$output, key, "output.json")
  if (!identical(file_sha256(path), workflow$records[[key]]$outputs[["output.json"]])) stop("Transfer input checksum mismatch: ", key)
  json_read(path)
}
workflow_context <- function(workflow, key, run_id) {
  parents <- unlist(workflow$config$jobs[[key]]$parents)
  values <- lapply(parents, function(parent) workflow_output(workflow, parent)); names(values) <- parents
  if (key == "database") values$submission <- workflow_output(workflow, "submission")
  input_transfer(key, values, workflow$records, workflow$settings)
  context <- list(key = key, settings = workflow$settings, job_settings = workflow_job_settings(workflow, key),
                  run_id = run_id, parents = if (length(values)) values else json_object())
  if (key %in% c("submission", "qc")) context$source <- input_source(workflow)
  if (key == "extract") context$extracted <- input_extract(workflow)
  job <- source_job(workflow$sources, key)
  context$sources <- list(job = job$job, component = job$group)
  context
}
workflow_record <- function(workflow, key, result, run_id, folder, runtime) {
  json_finite(result); json_write(result, file.path(folder, "output.json"))
  outputs <- list("output.json" = file_sha256(file.path(folder, "output.json")))
  if (key == "database") outputs[["snapshot.sqlite"]] <- file_sha256(file.path(folder, "snapshot.sqlite"))
  parents <- unlist(workflow$config$jobs[[key]]$parents)
  inputs <- lapply(parents, function(parent) {
    record <- workflow$records[[parent]]
    list(run_id = record$run_id, owner = record$owner,
      title = record$title %||% workflow$config$jobs[[parent]]$title,
      checksum = record$outputs[["output.json"]], signature = record$signature, analysis_source = record$analysis_source)
  }); names(inputs) <- parents
  if (!length(inputs)) inputs <- json_object()
  messages <- vapply(Filter(function(event) identical(event$job, key) || (event$state %in% c("handover", "received") && key %in% unlist(event$group)), workflow$events), function(event) event$message, character(1))
  code <- source_code(workflow$sources, key, workflow$execution$hosted, workflow$execution$local); origins <- source_code_origins(workflow$sources, key)
  for (name in setdiff(names(code), names(origins))) origins[[name]] <- c(source_coordinator(workflow$sources), list(path = name, sha256 = code[[name]]))
  record <- list(schema_version = 2L, job = key, title = workflow$config$jobs[[key]]$title,
    owner = workflow$config$jobs[[key]]$owner, run_id = run_id,
    signature = workflow_signature(workflow, key), settings = workflow_job_settings(workflow, key), snapshot = workflow$settings$last_year,
    code = code, code_sources = origins, analysis_source = source_origin(workflow$sources, key),
    software = runtime$software, coordinator_software = workflow_host_software(), runtime = (runtime$descriptor %||% runtime)[intersect(c("image", "image_id", "platform", "rootfs_diff_ids", "package_url", "repository", "commit", "entrypoint"), names(runtime$descriptor %||% runtime))], outputs = outputs,
    log = as.list(c(messages, paste0(workflow$config$jobs[[key]]$title, " complete."))), inputs = inputs,
    data_files = input_files(workflow), source = source_coordinator(workflow$sources))
  record$input_contract <- input_transfer(key, setNames(lapply(parents, function(parent) workflow_output(workflow, parent)), parents), workflow$records, workflow$settings)
  if (length(workflow$execution)) {
    record$execution <- workflow$execution
    record$execution$container <- runtime$software$container
    record$execution$image_id <- runtime$software$image_id
  }
  calculation_path <- file.path(folder, "container-inside-job.json")
  if (file.exists(calculation_path)) {
    calculation <- json_read(calculation_path)
    if (!identical(calculation$job, key) || calculation$exit_code != 0L ||
        !identical(calculation$running, FALSE) ||
        !identical(calculation$image_id, runtime$software$image_id))
      stop("Calculation receipt differs from the completed job: ", key)
    response_path <- file.path(folder, "response.json")
    # A QC correction may replace a submission without another container run.
    # Its earlier successful receipt does not establish the corrected result.
    if (file.exists(response_path) &&
        identical(json_encode(json_read(response_path)$result), json_encode(result)))
      record$execution$calculation <- calculation[c("container_id", "image_id", "exit_code", "started_at", "finished_at")]
  }
  source <- input_source(workflow)
  if (input_public(source)) record$data_source <- source$metadata
  record
}
workflow_finish_record <- function(workflow, key, record, rendering, folder) {
  if (!is.list(rendering) || !isTRUE(rendering$quarto_executed)) stop("A completed job requires a real Quarto rendering receipt: ", key)
  required <- unique(c("report.html", "report.pdf", "report.qmd", "report-data.json", unlist(rendering$artifacts, use.names = FALSE)))
  for (name in required) record$outputs[[name]] <- file_sha256(source_path(folder, name))
  pdf <- file(file.path(folder, "report.pdf"), "rb")
  header <- tryCatch(readBin(pdf, "raw", n = 5L), finally = close(pdf))
  if (!identical(header, charToRaw("%PDF-"))) stop("Quarto did not produce a valid PDF: ", key)
  record$report_rendering <- rendering
  json_write(record, file.path(folder, "record.json"))
  workflow$records[[key]] <- record
  workflow_persist(workflow)
  workflow_event(workflow, key, "complete", paste0(workflow$config$jobs[[key]]$title, " complete."))
  invisible(record)
}
workflow_effects <- function(workflow, key, response, run_id) {
  if (!is.list(response) || !setequal(names(response), c("result", "effects")) || !is.list(response$result) || !is.list(response$effects)) stop("Job response must contain exactly result and effects objects")
  json_finite(response)
  if (!length(response$effects)) return(invisible(NULL))
  if (key != "qc" || !identical(names(response$effects), "resubmit_submission")) stop("The R job requested undeclared side effects")
  workflow_event(workflow, "qc", "failed", "Zero effort found. Return the record to the data provider.")
  workflow_event(workflow, "submission", "returned", "The provider corrects the effort field.")
  workflow_event(workflow, "submission", "running", "The provider resubmits the corrected records.", activity = "resubmit")
  runtime <- workflow_runtime(workflow, "submission"); folder <- file.path(workflow$output, "submission")
  result <- response$effects$resubmit_submission
  record <- workflow_record(workflow, "submission", result, run_id, folder, runtime)
  rendering <- workflow_backend(workflow, "render", workflow$config$jobs$submission, result, record, folder, runtime, workflow$sources)
  workflow_finish_record(workflow, "submission", record, rendering, folder)
  workflow_event(workflow, "qc", "running", "Check the corrected submission.")
}
workflow_handovers <- function(workflow, keys, selected) {
  result <- list()
  for (boundary in names(workflow$config$handovers)) {
    recipients <- workflow$config$handovers[[boundary]]
    group <- keys[vapply(keys, function(key) key %in% names(recipients) && any(unlist(recipients[[key]]) %in% selected), logical(1))]
    if (length(group)) result[[length(result) + 1L]] <- list(boundary = boundary, group = as.list(group))
  }
  result
}
workflow_run <- function(workflow, start = "submission", scope = "workflow") {
  if (isTRUE(workflow$running)) stop("An execution is already in progress")
  if (.Platform$OS.type != "unix") stop("Concurrent job dispatch requires a POSIX host")
  limits <- workflow$execution$max_workers %||% 4L
  if (!is.numeric(limits) || length(limits) != 1L || !is.finite(limits) || limits < 1 || limits != as.integer(limits)) stop("max_workers must be a positive integer")
  workflow$running <- TRUE; workers <- list(); transfer <- NULL
  on.exit({
    for (key in names(workers)) {
      worker <- workers[[key]]
      try(tools::pskill(worker$process$pid, 15L), silent = TRUE)
      cancel <- workflow$runtime_backend$cancel
      if (is.null(cancel) && exists("runtime_cancel", mode = "function")) cancel <- get("runtime_cancel", mode = "function")
      if (!is.null(cancel)) try(cancel(workflow$config$jobs[[key]], worker$folder, worker$runtime), silent = TRUE)
    }
    if (!is.null(transfer)) try(tools::pskill(transfer$process$pid, 15L), silent = TRUE)
    workflow$running <- FALSE
  }, add = TRUE)
  workflow$events <- list(); workflow$runtimes <- list()
  plan <- workflow_plan(workflow, start, scope); workflow$last_plan <- plan
  workflow$run_number <- workflow$run_number + 1L; run_id <- sprintf("Run %03d", workflow$run_number)
  workflow$notify(c(list(state = "plan", run_id = run_id), plan), workflow_state(workflow), workflow$output)
  selected <- unlist(plan$run, use.names = FALSE)
  stages <- lapply(workflow$config$stages, function(stage) intersect(unlist(stage), selected)); stages <- Filter(length, stages)
  status <- rep("pending", length(stages)); stage_for <- setNames(rep(seq_along(stages), lengths(stages)), unlist(stages))
  jobs <- workflow$config$jobs; pending <- character(); completed <- character(); errors <- list(); transfers_done <- integer()
  stage_parents <- lapply(seq_along(stages), function(i) setdiff(unique(unname(stage_for[intersect(unlist(lapply(jobs[stages[[i]]], function(job) job$parents)), selected)])), i))
  fail <- function(key, error) {
    message <- if (inherits(error, "condition")) conditionMessage(error) else as.character(error)
    workflow$records[[key]] <- NULL; workflow_persist(workflow)
    workflow_event(workflow, key, "failed", message); errors[[key]] <<- message
  }
  spawn <- function(fun) parallel::mcparallel(tryCatch(list(ok = TRUE, value = fun()), error = function(error) list(ok = FALSE, error = conditionMessage(error))), silent = TRUE, mc.set.seed = FALSE)
  collect <- function(process) {
    value <- parallel::mccollect(process, wait = FALSE)
    if (is.null(value)) return(NULL)
    value <- value[[1L]]
    if (!is.list(value) || is.null(value$ok)) return(list(ok = FALSE, error = "Worker ended without a valid response"))
    value
  }
  while (any(status %in% c("pending", "transfer", "running")) || length(workers)) {
    # Collect first so unrelated report branches keep progressing during a transfer.
    for (key in names(workers)) {
      worker <- workers[[key]]; value <- collect(worker$process)
      if (is.null(value)) next
      workers[[key]] <- NULL
      if (!isTRUE(value$ok)) { fail(key, value$error); next }
      if (worker$phase == "calculate") {
        response <- value$value
        prepared <- tryCatch({
          workflow_effects(workflow, key, response, run_id)
          if (key == "database") input_snapshot(workflow, worker$context$parents$submission, worker$folder)
          record <- workflow_record(workflow, key, response$result, run_id, worker$folder, worker$runtime)
          list(record = record, result = response$result)
        }, error = identity)
        if (inherits(prepared, "condition")) { fail(key, prepared); next }
        workflow_event(workflow, key, "activity", "Compiling the saved results to PDF.", activity = "rendering", title = "Generating the result PDF")
        process <- spawn(function() workflow_backend(workflow, "render", jobs[[key]], prepared$result, prepared$record, worker$folder, worker$runtime, workflow$sources))
        workers[[key]] <- c(worker[c("folder", "runtime")], list(process = process, phase = "render", record = prepared$record))
      } else {
        done <- tryCatch(workflow_finish_record(workflow, key, worker$record, value$value, worker$folder), error = identity)
        if (inherits(done, "condition")) fail(key, done) else completed <- c(completed, key)
      }
    }
    if (!is.null(transfer)) {
      value <- collect(transfer$process)
      if (!is.null(value)) {
        i <- transfer$stage; boundary <- transfer$boundary
        if (!isTRUE(value$ok)) {
          status[[i]] <- "failed"; for (key in stages[[i]]) fail(key, value$error)
        } else {
          acknowledgment <- value$value
          workflow$handover_state <- acknowledgment
          connected <- isTRUE(acknowledgment) || (is.list(acknowledgment) && isTRUE(acknowledgment$connected))
          if (connected) workflow$handover <- NULL
          workflow_event(workflow, unlist(boundary$group)[[1]], "received", paste0("File transfer confirmed for ", paste(unlist(boundary$group), collapse = " and "), "."), boundary = boundary$boundary, group = boundary$group)
          transfers_done <- c(transfers_done, i); status[[i]] <- "pending"
        }
        transfer <- NULL
      }
    }
    for (i in seq_along(stages)) {
      if (status[[i]] == "running" && !any(stages[[i]] %in% c(names(workers), pending))) {
        status[[i]] <- if (any(stages[[i]] %in% names(errors))) "failed" else "done"
      }
      if (status[[i]] != "pending") next
      parents <- stage_parents[[i]]
      if (any(status[parents] %in% c("failed", "blocked"))) {
        status[[i]] <- "blocked"
        for (key in stages[[i]]) fail(key, "A required input group failed")
        next
      }
      if (length(parents) && !all(status[parents] == "done")) next
      boundaries <- workflow_handovers(workflow, stages[[i]], selected)
      if (!is.null(workflow$handover) && length(boundaries) && !i %in% transfers_done) {
        if (!is.null(transfer)) next
        boundary <- boundaries[[1L]]
        workflow_event(workflow, unlist(boundary$group)[[1]], "handover", "Updated inputs are ready. Confirm file transfer to continue.", boundary = boundary$boundary, group = boundary$group)
        callback <- workflow$handover
        transfer <- list(stage = i, boundary = boundary, process = spawn(function() callback(boundary$boundary, unlist(boundary$group))))
        status[[i]] <- "transfer"; next
      }
      status[[i]] <- "running"; pending <- c(pending, stages[[i]])
    }
    while (length(pending) && length(workers) < limits) {
      key <- pending[[1L]]; pending <- pending[-1L]
      worker <- tryCatch({
        source_verify(workflow$sources)
        runtime <- workflow_runtime(workflow, key); context <- workflow_context(workflow, key, run_id)
        folder <- file.path(workflow$output, key); dir.create(folder, recursive = TRUE, showWarnings = FALSE)
        workflow$records[[key]] <- NULL; workflow_persist(workflow)
        workflow_event(workflow, key, "running", jobs[[key]]$description, group = as.list(stages[[stage_for[[key]]]]))
        workflow_event(workflow, key, "activity", "Running this job's Makefile and R code.", activity = "calculating", title = "Calculating")
        process <- spawn(function() workflow_backend(workflow, "calculate", jobs[[key]], context, folder, runtime))
        list(process = process, phase = "calculate", runtime = runtime, context = context, folder = folder)
      }, error = identity)
      if (inherits(worker, "condition")) fail(key, worker) else workers[[key]] <- worker
    }
    if (length(workers) || !is.null(transfer)) Sys.sleep(0.05)
  }
  workflow_persist(workflow)
  if (length(errors)) stop(paste(unique(unlist(errors)), collapse = "; "))
  c(list(run_id = run_id), plan, workflow_state(workflow))
}
workflow_runtime_catalogue <- function(workflow) {
  catalogue <- list()
  add <- function(runtime, software, job, role, run_id) {
    if (is.null(runtime) && is.null(software$container)) return(invisible(NULL))
    descriptor <- runtime %||% list(image = software$container, image_id = software$image_id,
      platform = software$platform, rootfs_diff_ids = software$rootfs_diff_ids)
    material <- descriptor[intersect(c("image", "image_id", "platform", "rootfs_diff_ids"), names(descriptor))]
    if (is.null(material$image_id) || is.null(material$platform) || is.null(material$rootfs_diff_ids)) stop("Saved runtime lacks offline identity: ", job, " ", role)
    id <- value_sha256(material)
    if (is.null(catalogue[[id]])) catalogue[[id]] <<- c(material, list(archive = paste0("runtime-images/", sub("^sha256:", "", material$image_id), ".tar"), uses = list()))
    catalogue[[id]]$uses[[length(catalogue[[id]]$uses) + 1L]] <<- list(job = job, role = role, run_id = run_id)
  }
  for (key in names(workflow$records)) {
    record <- workflow$records[[key]]
    add(record$runtime, record$software, key, "calculation", record$run_id)
    renderer <- record$report_rendering
    if (!is.null(renderer$runtime) || !is.null(renderer$software)) add(renderer$runtime, renderer$software %||% record$software, key, "rendering", record$run_id)
    else add(record$runtime, record$software, key, "rendering", record$run_id)
  }
  list(schema_version = 2L, images = catalogue,
    preservation = "Save each listed image with docker image save. Verify image config, platform and ordered rootfs diff IDs after restoring. Offline execution disables pull and container networking.")
}
workflow_bundle <- function(workflow, path) {
  source_verify(workflow$sources)
  stage <- tempfile("workflow-bundle-"); dir.create(stage); on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  root <- workflow$root
  names <- list.files(root, recursive = TRUE, all.files = TRUE, no.. = TRUE)
  keep <- grepl("^(R/|app/|tests-r/|workflow/.*\\.(json|sql|qmd|R)$|scripts/.*\\.(R|sh)$|data/|jobs/.*\\.(R|qmd|md)$)", names) |
    names %in% c("Makefile", "README.md", "OFFLINE.md", "ADAPT.md", "LICENSE", "THIRD_PARTY.md", "build-info.json", "coordinator-origin.json", "source-files.sha256.json", "source-lock.template.json")
  names <- names[keep & !dir.exists(file.path(root, names))]
  origin_file <- file.path(root, "coordinator-origin.json")
  if (file.exists(origin_file)) names <- union(names, names(json_read(origin_file)$files))
  receipt_file <- file.path(root, "data/public-data.json")
  if (file.exists(receipt_file)) names <- union(names, json_read(receipt_file)$adapter$path)
  if (file.exists(file.path(root, "runtime-overrides.json"))) names <- union(names, "runtime-overrides.json")
  for (name in names) {
    source <- source_path(root, name); dest <- source_path(stage, name, exists = FALSE)
    dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
    if (!file.copy(source, dest)) stop("Cannot archive coordinator source: ", name)
  }
  source_archive(workflow$sources, stage)
  if (!is.null(workflow$hosted_data)) writeBin(charToRaw(json_encode(workflow$hosted_data)), file.path(stage, "data/frozen-source.json"))
  dir.create(file.path(stage, "reference"))
  saved <- c("state.json", unlist(lapply(names(workflow$records), function(key) {
    paste0(key, "/", c("record.json", names(workflow$records[[key]]$outputs)))
  }), use.names = FALSE))
  # Preserve every recorded artifact; context, response and cache files are scratch.
  for (name in unique(saved)) {
    dest <- source_path(file.path(stage, "reference"), name, exists = FALSE)
    dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
    if (!file.copy(source_path(workflow$output, name), dest)) stop("Cannot archive reference: ", name)
  }
  settings <- workflow$settings
  if (!is.null(workflow$last_plan) && identical(workflow$last_plan$scope, "job")) settings <- json_read(file.path(workflow$output, "state.json"))$settings
  if (!is.null(workflow$records$mse_buffered)) settings$mse_buffer <- workflow$records$mse_buffered$settings$buffer %||% 0.8
  json_write(settings, file.path(stage, "settings.json"))
  json_write(workflow_runtime_catalogue(workflow), file.path(stage, "runtime-catalogue.json"))
  # A retained job may have been produced by an earlier image than today's mapping.
  overrides <- list()
  for (key in names(workflow$records)) {
    record <- workflow$records[[key]]
    overrides[[key]] <- record$runtime[intersect(c("image", "platform", "package_url"), names(record$runtime))]
  }
  json_write(list(schema_version = 1L, jobs = overrides), file.path(stage, "runtime-preserved.json"))
  target <- if (identical(workflow$last_plan$scope, "job")) workflow$last_plan$start else NULL
  command <- paste0("make reproduce", if (!is.null(target)) paste0(" JOB=", shQuote(target)) else "")
  writeLines(c("Host prerequisites: R with jsonlite, digest, DBI and RSQLite; Make; Docker; POSIX shell.",
    "Restore every required image listed in runtime-catalogue.json from your saved image archives.",
    "Verify the preserved sources and image identities before running with pull and container networking disabled.",
    paste0("Run: ", command), "New results belong in offline-runs/; reference/ preserves the original producing runs.",
    if (!is.null(target)) paste0("This bundle reproduces only ", target, "; other records retain their original run identities.") else ""), file.path(stage, "REPRODUCE.txt"))
  names <- list.files(stage, recursive = TRUE, all.files = TRUE, no.. = TRUE)
  names <- names[!dir.exists(file.path(stage, names))]
  hashes <- lapply(setNames(file.path(stage, names), names), file_sha256)
  json_write(hashes, file.path(stage, "SHA256SUMS.json"))
  path <- file.path(normalizePath(dirname(path), mustWork = TRUE), basename(path))
  previous <- setwd(stage); on.exit(setwd(previous), add = TRUE)
  status <- utils::zip(path, files = c(names, "SHA256SUMS.json"), flags = "-q")
  if (status != 0L || !file.exists(path)) stop("Cannot create workflow archive")
  invisible(path)
}
