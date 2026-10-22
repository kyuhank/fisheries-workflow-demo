# One loopback browser coordinates local R/Make jobs using preserved sources.
local_uuid <- function() {
  con <- file('/dev/urandom', 'rb', raw = TRUE); on.exit(close(con), add = TRUE)
  bytes <- as.integer(readBin(con, 'raw', 16L))
  if (length(bytes) != 16L) stop('Cannot create a session capability')
  bytes[[7L]] <- bitwOr(bitwAnd(bytes[[7L]], 15L), 64L)
  bytes[[9L]] <- bitwOr(bitwAnd(bytes[[9L]], 63L), 128L)
  hex <- paste(sprintf('%02x', bytes), collapse = '')
  paste(substring(hex, 1L, 8L), substring(hex, 9L, 12L), substring(hex, 13L, 16L),
        substring(hex, 17L, 20L), substring(hex, 21L, 32L), sep = '-')
}
local_bytes <- function(path) readBin(path, 'raw', n = file.info(path)$size)
local_base64 <- function(path) gsub('\n', '', jsonlite::base64_enc(local_bytes(path)), fixed = TRUE)
local_read <- function(path, default = NULL) if (file.exists(path)) json_read(path) else default
local_error <- function(message, status = 400L, code = NULL) stop(structure(
  list(message = message, call = NULL, status = status, code = code), class = c('local_error', 'error', 'condition')))
local_integer <- function(value, minimum = 0, maximum = .Machine$integer.max) is.numeric(value) &&
  length(value) == 1L && is.finite(value) && value == floor(value) && value >= minimum && value <= maximum
local_check <- function(root, images = TRUE) {
  release_manifest(root)
  sources <- new_sources(root)
  if (!isTRUE(sources$snapshot)) stop('Local offline runs require preserved component source snapshots')
  source_verify(sources)
  catalogue <- offline_catalogue(root)
  if (images) for (image in catalogue$images) offline_image(image)
  invisible(list(sources = sources, catalogue = catalogue))
}
local_new <- function(root, workspace, port = 8765L, verify = TRUE) {
  if (.Platform$OS.type != 'unix') stop('Local execution requires a POSIX host')
  if (!local_integer(port, 1024, 65535)) stop('Choose a port from 1024 to 65535')
  root <- normalizePath(root, mustWork = TRUE)
  dir.create(workspace, recursive = TRUE, mode = '0700', showWarnings = FALSE)
  workspace <- normalizePath(workspace, mustWork = TRUE)
  if (identical(workspace, root) || startsWith(workspace, paste0(root, '/')) || startsWith(root, paste0(workspace, '/')))
    stop('Choose a separate workspace outside the extracted source folder')
  for (previous in list.dirs(workspace, recursive = FALSE, full.names = TRUE)) {
    owner <- local_read(file.path(previous, 'owner.json'))
    if (is.null(owner) || !identical(owner$root, root) || !identical(owner$owner, basename(previous))) next
    statuses <- list.files(previous, pattern = '^status\\.json$', recursive = TRUE, full.names = TRUE)
    for (path in statuses) if (local_read(path)$status %in% c('queued', 'running', 'handover'))
      stop('An earlier local run has no completion receipt. Inspect its preserved state before using this workspace: ', path)
  }
  if (verify) local_check(root)
  backend <- new.env(parent = emptyenv())
  backend$root <- root; backend$workspace <- workspace; backend$port <- as.integer(port)
  backend$origin <- paste0('http://127.0.0.1:', port); backend$owner <- local_uuid()
  backend$directory <- file.path(workspace, backend$owner)
  dir.create(backend$directory, mode = '0700'); backend$sessions <- list(); backend$workers <- list()
  backend$config <- workflow_spec(root)
  backend$page <- if (file.exists(file.path(root, 'docs/index.html'))) file.path(root, 'docs/index.html') else file.path(root, 'index.html')
  if (!file.exists(backend$page)) stop('The saved bundle must include its built index.html')
  backend$public <- local_payload(backend$page)$payload$cloud
  receipt <- json_read(file.path(root, 'data/public-data.json'))
  backend$public$source_sha256 <- receipt$output_sha256
  backend$public$data_kind <- 'public-wcpfc-albacore'
  json_write(list(schema_version = 1L, owner = backend$owner, pid = Sys.getpid(), root = root,
    created = format(Sys.time(), tz = 'UTC', usetz = TRUE)), file.path(backend$directory, 'owner.json'))
  backend
}
local_session <- function(backend) {
  if (length(backend$sessions) >= 20L) local_error('Close this local service before starting more sessions.', 429L)
  id <- local_uuid(); token <- paste0(gsub('-', '', local_uuid(), fixed = TRUE), gsub('-', '', local_uuid(), fixed = TRUE))
  directory <- file.path(backend$directory, id); dir.create(directory, mode = '0700')
  session <- list(id = id, token = token, directory = directory, owner = backend$owner)
  json_write(session, file.path(directory, 'session.json'))
  backend$sessions[[id]] <- session
  list(id = id, token = token)
}
local_authenticate <- function(backend, id, authorization) {
  if (!is.character(id) || length(id) != 1L || is.null(backend$sessions[[id]]) ||
      !identical(authorization, paste('Bearer', backend$sessions[[id]]$token)))
    local_error('This local session is unavailable. Select Start afresh.', 403L, 'session_denied')
  backend$sessions[[id]]
}
local_run_directory <- function(session, request) source_path(session$directory, paste0('requests/', request))
local_current <- function(session) local_read(file.path(session$directory, 'current.json'))
local_status <- function(session) {
  current <- local_current(session)
  if (is.null(current)) return(NULL)
  local_read(file.path(local_run_directory(session, current$id), 'status.json'))
}
local_settings <- function(backend, body) {
  if (!is.list(body) || anyDuplicated(names(body)) || !setequal(names(body), c('start', 'settings', 'handover', if ('scope' %in% names(body)) 'scope')) ||
      !is.character(body$start) || length(body$start) != 1L || !body$start %in% names(backend$config$jobs) ||
      !is.character(body$handover) || length(body$handover) != 1L || !body$handover %in% c('manual', 'connected') ||
      (!is.null(body$scope) && (!is.character(body$scope) || length(body$scope) != 1L)) ||
      ('scope' %in% names(body) && is.null(body$scope)) || !(body$scope %||% 'workflow') %in% c('job', 'workflow')) local_error('Select a job, execution scope and handover mode.')
  settings <- body$settings; keys <- names(settings)
  allowed <- c('last_year', 'min_hooks_a', 'growth_rate_2', 'mse', 'mse_buffer')
  if (!is.list(settings) || anyDuplicated(keys) || !all(c('last_year', 'min_hooks_a', 'growth_rate_2') %in% keys) ||
      !all(keys %in% allowed) || ('mse_buffer' %in% keys && !'mse' %in% keys))
    local_error('Select the supplied demonstration settings.')
  member <- function(value, choices) is.numeric(value) && length(value) == 1L && is.finite(value) && value %in% choices
  if (!member(settings$last_year, c(2021, 2022)) || !member(settings$min_hooks_a, c(0, 1200)) ||
      !member(settings$growth_rate_2, c(.25, .30, .35)) ||
      ('mse' %in% keys && (!is.logical(settings$mse) || length(settings$mse) != 1L || is.na(settings$mse))) ||
      ('mse_buffer' %in% keys && !member(settings$mse_buffer, c(.6, .8, 1))) ||
      (startsWith(body$start, 'mse_') && !isTRUE(settings$mse))) local_error('Select the supplied demonstration settings.')
  utils::modifyList(list(mse = FALSE), settings)
}
local_event <- function(directory, event, state, number, request) {
  control <- json_read(file.path(directory, 'control.json'))
  if (identical(event$state, 'handover')) {
    event$request_id <- request$id; event$transfer_count <- control$transfer_count
    json_write(list(request_id = request$id, transfer_count = control$transfer_count,
      boundary = event$boundary, group = event$group), file.path(directory, 'waiting.json'))
  } else if (identical(event$state, 'received')) unlink(file.path(directory, 'waiting.json'))
  json_write(list(id = number, event = event), file.path(directory, 'events', sprintf('%012d.json', number)))
  json_write(state, file.path(directory, 'state.json'))
  status <- request; status$status <- if (file.exists(file.path(directory, 'waiting.json'))) 'handover' else 'running'
  json_write(status, file.path(directory, 'status.json'))
  invisible(event)
}
local_handover <- function(directory, count, timeout = 180) {
  deadline <- Sys.time() + timeout
  while (Sys.time() < deadline) {
    control <- json_read(file.path(directory, 'control.json'))
    if (isTRUE(control$cancelled)) stop('Local execution was cancelled')
    if (control$transfer_count > count || isTRUE(control$connected))
      return(list(transfer_count = control$transfer_count, connected = isTRUE(control$connected)))
    Sys.sleep(.2)
  }
  stop('File transfer was not acknowledged within three minutes. Start again to continue.')
}
local_payload <- function(path) {
  html <- paste(readLines(path, warn = FALSE, encoding = 'UTF-8'), collapse = '\n')
  pattern <- '<script id="demo-payload" type="application/json">\\s*(.*?)\\s*</script>'
  match <- regmatches(html, regexec(pattern, html, perl = TRUE))[[1L]]
  if (length(match) != 2L) stop('The built page has no saved workflow payload')
  list(html = html, match = match[[1L]], payload = jsonlite::fromJSON(match[[2L]], simplifyVector = FALSE))
}
local_page <- function(backend) {
  page <- local_payload(backend$page); payload <- page$payload
  payload$cloud$url <- paste0(backend$origin, '/api'); payload$cloud$provider <- 'local'
  payload$local <- list(provider = 'local', offline = TRUE, url = backend$origin)
  payload$calculationBackend <- 'local'; payload$offlineMode <- 'local'
  encoded <- gsub('</', '<\\/', json_encode(payload), fixed = TRUE)
  replacement <- paste0('<script id="demo-payload" type="application/json">', encoded, '</script>')
  sub(page$match, replacement, page$html, fixed = TRUE)
}
local_bundle <- function(backend, workflow, directory) {
  original <- file.path(directory, 'workflow.zip'); readers <- file.path(directory, 'readers.zip')
  workflow_bundle(workflow, original)
  version <- json_read(file.path(backend$root, 'build-info.json'))$version
  release_saved_bundle(original, readers, version)
  stage <- tempfile('local-bundle-'); dir.create(stage); on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  release_unpack(readers, stage)
  base <- dirname(backend$page)
  for (name in c('data.html', 'data/fiji-source.csv', 'data/annual-catch.csv', 'data/extract.sql')) {
    if (file.exists(file.path(base, name))) {
      destination <- source_path(stage, name, exists = FALSE); dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)
      file.copy(file.path(base, name), destination, overwrite = TRUE)
    }
  }
  release_manifest(stage, verify = FALSE)
  release_zip(stage, file.path(directory, 'bundle.zip'))
}
local_worker <- function(backend, session, request, body) {
  directory <- local_run_directory(session, request$id)
  output <- file.path(session$directory, 'results')
  # The parent alone serves HTTP; this child writes only its private session files.
  Sys.setenv(PAPER_OFFLINE = '1', PAPER_DOCKER_PULL = 'never', PAPER_DATA_MODE = 'public')
  options(workflow.root = backend$root)
  count <- 0L; transfer_count <- 0L; runner <- NULL; result <- NULL; error <- NULL
  notify <- function(event, state, output = NULL) {
    if (identical(event$state, 'received') && !is.null(state$handover_state$transfer_count)) transfer_count <<- state$handover_state$transfer_count
    count <<- count + 1L; local_event(directory, event, state, count, request)
  }
  tryCatch({
    local_check(backend$root)
    handover <- if (identical(body$handover, 'manual')) function(boundary, group) local_handover(directory, transfer_count) else NULL
    packages <- c('jsonlite', 'digest', 'DBI', 'RSQLite', 'httpuv')
    execution <- list(provider = 'Local', local = TRUE, offline = TRUE, max_workers = 2L,
      coordinator = list(R = R.version.string, platform = R.version$platform,
        packages = setNames(lapply(packages, function(package) as.character(utils::packageVersion(package))), packages)))
    runner <- new_workflow(output, settings = local_settings(backend, body), notify = notify,
      handover = handover, execution = execution)
    notify(list(state = 'phase', title = 'Preparing local analyses', message = 'Using the preserved sources and locally restored job images.'), workflow_state(runner))
    result <- workflow_run(runner, body$start, body$scope %||% 'workflow')
    local_bundle(backend, runner, directory)
  }, error = function(caught) error <<- conditionMessage(caught), interrupt = function(caught) error <<- 'Local execution was cancelled')
  final <- request; final$status <- if (is.null(error)) 'complete' else 'failed'
  final$result <- result; final$error <- error
  if (!is.null(runner)) json_write(workflow_state(runner), file.path(directory, 'state.json'))
  if (is.null(error)) final$bundle_sha256 <- file_sha256(file.path(directory, 'bundle.zip'))
  json_write(final, file.path(directory, 'status.json'))
  invisible(list(status = final$status))
}
local_reap <- function(backend) {
  for (request in names(backend$workers)) {
    worker <- backend$workers[[request]]
    value <- parallel::mccollect(worker$process, wait = FALSE)
    if (is.null(value)) next
    backend$workers[[request]] <- NULL
    status <- local_status(worker$session)
    if (!is.null(status) && identical(status$id, request) && status$status %in% c('queued', 'running', 'handover')) {
      status$status <- 'failed'; status$error <- 'The local worker stopped before publishing a complete run.'
      json_write(status, file.path(local_run_directory(worker$session, request), 'status.json'))
    }
  }
  invisible(NULL)
}
local_dispatch <- function(backend, session, body) {
  local_reap(backend); settings <- local_settings(backend, body)
  current <- local_status(session)
  if (!is.null(current) && current$status %in% c('queued', 'running', 'handover')) local_error('Wait for the current local run.', 409L)
  # All source/runtime verification runs before models, never by fetching code.
  local_check(backend$root, images = FALSE)
  request <- list(id = local_uuid(), status = 'queued', provider = 'Local', github_run = NULL,
    start_job = body$start, scope = body$scope %||% 'workflow', settings = settings, handover = body$handover)
  directory <- file.path(session$directory, 'requests', request$id); dir.create(directory, recursive = TRUE, mode = '0700')
  json_write(request, file.path(directory, 'status.json')); json_write(list(id = request$id), file.path(session$directory, 'current.json'))
  json_write(list(transfer_count = 0L, connected = identical(body$handover, 'connected'), cancelled = FALSE), file.path(directory, 'control.json'))
  process <- parallel::mcparallel(local_worker(backend, session, request, body), silent = TRUE, mc.set.seed = FALSE)
  backend$workers[[request$id]] <- list(process = process, session = session)
  list(id = request$id, status = 'queued')
}
local_transfer <- function(session, body) {
  if (!is.list(body) || !setequal(names(body), c('request_id', 'transfer_count', 'connect')) ||
      !is.character(body$request_id) || length(body$request_id) != 1L || !local_integer(body$transfer_count) ||
      !is.logical(body$connect) || length(body$connect) != 1L || is.na(body$connect)) local_error('Invalid file transfer identity.')
  status <- local_status(session)
  if (is.null(status) || !identical(status$id, body$request_id)) local_error('This transfer does not belong to the current local run.')
  directory <- local_run_directory(session, status$id); control <- json_read(file.path(directory, 'control.json'))
  replay <- control$transfer_count > body$transfer_count
  if (!replay) {
    waiting <- local_read(file.path(directory, 'waiting.json'))
    if (is.null(waiting) || !status$status %in% c('running', 'handover') ||
        !identical(as.numeric(waiting$transfer_count), as.numeric(body$transfer_count)) || control$transfer_count != body$transfer_count)
      local_error('This file transfer is not pending. Wait for the current status.')
    control$transfer_count <- control$transfer_count + 1L; control$connected <- body$connect
    json_write(control, file.path(directory, 'control.json'))
  }
  list(ok = TRUE, request_id = status$id, transfer_count = control$transfer_count, connected = control$connected, replay = replay)
}
local_output <- function(session, key) {
  output <- file.path(session$directory, 'results'); state <- local_read(file.path(output, 'state.json'))
  record <- state$records[[key]]
  if (is.null(record)) local_error('This output is not ready.', 409L)
  folder <- source_path(output, key)
  for (name in c('output.json', 'report.html', 'report.pdf')) if (!identical(file_sha256(source_path(folder, name)), record$outputs[[name]])) local_error('The saved output checksum differs.', 409L)
  list(html = rawToChar(local_bytes(file.path(folder, 'report.html'))),
    pdf_base64 = local_base64(file.path(folder, 'report.pdf')), record = record, output = json_read(file.path(folder, 'output.json')))
}
local_api <- function(backend, method, path, query = list(), body = NULL, authorization = '') {
  local_reap(backend)
  if (path == '/info' && method == 'GET') return(c(backend$public[c('repository', 'data_kind', 'source_sha256')], list(configured = TRUE, provider = 'local')))
  if (path == '/session' && method == 'POST') return(local_session(backend))
  session <- local_authenticate(backend, query$session %||% '', authorization)
  if (path == '/state' && method == 'GET') {
    cursor <- suppressWarnings(as.numeric(query$after %||% '0'))
    if (!local_integer(cursor)) local_error('Invalid event cursor.')
    status <- local_status(session); state <- NULL; events <- list()
    if (!is.null(status)) {
      directory <- local_run_directory(session, status$id); state <- local_read(file.path(directory, 'state.json'))
      names <- list.files(file.path(directory, 'events'), pattern = '^[0-9]{12}\\.json$', full.names = TRUE)
      for (name in names) { row <- json_read(name); if (row$id > cursor && length(events) < 100L) events[[length(events) + 1L]] <- row }
    }
    return(list(run = status, state = state, events = events))
  }
  if (path == '/output' && method == 'GET') {
    key <- query$job %||% ''; if (!key %in% names(backend$config$jobs)) local_error('Unknown job.')
    return(local_output(session, key))
  }
  if (path == '/bundle' && method == 'GET') {
    status <- local_status(session)
    if (is.null(status) || !identical(status$status, 'complete')) local_error('Download after a successful local run.', 409L)
    path <- file.path(local_run_directory(session, status$id), 'bundle.zip')
    if (!identical(file_sha256(path), status$bundle_sha256)) local_error('The saved bundle checksum differs.', 409L)
    return(list(request_id = status$id, bundle = local_base64(path)))
  }
  if (path == '/run' && method == 'POST') return(local_dispatch(backend, session, body))
  if (path == '/transfer' && method == 'POST') return(local_transfer(session, body))
  if (path == '/reset' && method == 'POST') {
    status <- local_status(session)
    if (!is.null(status) && status$status %in% c('queued', 'running', 'handover')) local_error('Wait for the current local run.', 409L)
    backend$sessions[[session$id]] <- NULL
    return(list(records = json_object()))
  }
  local_error('Unknown local operation.', 404L)
}
local_query <- function(value) {
  if (!nzchar(value %||% '')) return(list())
  result <- list()
  for (pair in strsplit(value, '&', fixed = TRUE)[[1L]]) {
    pieces <- strsplit(pair, '=', fixed = TRUE)[[1L]]; key <- utils::URLdecode(pieces[[1L]])
    if (!key %in% c('session', 'after', 'job') || !is.null(result[[key]]) || length(pieces) != 2L) local_error('Invalid local query.')
    result[[key]] <- utils::URLdecode(pieces[[2L]])
  }
  result
}
local_response <- function(status = 200L, value = NULL, body = NULL, type = 'application/json') list(status = status,
  headers = list('Content-Type' = paste0(type, '; charset=utf-8'), 'Cache-Control' = 'no-store', 'X-Content-Type-Options' = 'nosniff'),
  body = if (is.null(body)) json_encode(value) else body)
local_http <- function(backend, request) tryCatch({
  host <- request$HTTP_HOST %||% ''; origin <- request$HTTP_ORIGIN %||% ''
  if (!identical(host, paste0('127.0.0.1:', backend$port)) || (nzchar(origin) && !identical(origin, backend$origin))) local_error('Use this server from its loopback page.', 403L)
  method <- request$REQUEST_METHOD; path <- request$PATH_INFO %||% '/'
  if (method == 'POST' && (!identical(origin, backend$origin) || !startsWith(request$CONTENT_TYPE %||% '', 'application/json'))) local_error('Use a same-origin JSON request.', 403L)
  if (startsWith(path, '/api/')) {
    body <- NULL
    if (method == 'POST') {
      bytes <- request$rook.input$read(8193L)
      if (length(bytes) > 8192L) local_error('Request too large.', 413L)
      body <- jsonlite::fromJSON(if (is.raw(bytes)) rawToChar(bytes) else bytes, simplifyVector = FALSE)
    }
    return(local_response(value = local_api(backend, method, substring(path, 5L), local_query(request$QUERY_STRING), body, request$HTTP_AUTHORIZATION %||% '')))
  }
  if (!identical(method, 'GET')) local_error('Use GET.', 405L)
  if (path %in% c('/', '/index.html', '/offline.html')) return(local_response(body = local_page(backend), type = 'text/html'))
  relative <- sub('^/', '', utils::URLdecode(path))
  base <- dirname(backend$page)
  if (startsWith(relative, 'example/') && !dir.exists(file.path(base, 'example')) && dir.exists(file.path(backend$root, 'reference'))) {
    relative <- sub('^example/', '', relative); base <- file.path(backend$root, 'reference')
  }
  file <- tryCatch(source_path(base, relative), error = function(error) NULL)
  if (is.null(file) || dir.exists(file)) local_error('File not found.', 404L)
  extension <- tolower(tools::file_ext(file)); types <- c(html = 'text/html', pdf = 'application/pdf', json = 'application/json', csv = 'text/csv', sql = 'text/plain', md = 'text/plain', txt = 'text/plain', r = 'text/plain', sh = 'text/plain', yaml = 'text/plain', yml = 'text/plain', cff = 'text/plain', svg = 'image/svg+xml', png = 'image/png', zip = 'application/zip')
  if (identical(basename(file), 'Makefile')) return(local_response(body = local_bytes(file), type = 'text/plain'))
  if (!extension %in% names(types)) local_error('File not found.', 404L)
  local_response(body = local_bytes(file), type = unname(types[[extension]]))
}, local_error = function(error) local_response(error$status, c(list(error = conditionMessage(error)), if (!is.null(error$code)) list(code = error$code))),
  error = function(error) local_response(400L, list(error = conditionMessage(error))))
local_cleanup_containers <- function(output, jobs) {
  if (!dir.exists(output)) return(invisible(NULL))
  names <- list.files(output, pattern = '^active-container-(info|inside-job|render)\\.json$', recursive = TRUE, all.files = TRUE)
  for (name in names) {
    path <- source_path(output, name); folder <- normalizePath(dirname(path)); receipt <- json_read(path)
    if (!receipt$job %in% names(jobs) || !identical(receipt$output, value_sha256(folder)) ||
        !grepl('^[a-f0-9]{64}$', receipt$container_id %||% '') || !grepl('^sha256:[a-f0-9]{64}$', receipt$image_id %||% '')) stop('Invalid local container ownership receipt')
    found <- runtime_process('docker', c('inspect', receipt$container_id), timeout = 20)
    if (found$status != 0L) next
    actual <- jsonlite::fromJSON(found$stdout, simplifyVector = FALSE)[[1L]]
    labels <- actual$Config$Labels
    if (!identical(actual$Image, receipt$image_id) || !identical(labels[['org.fisheries-workflow.job']], receipt$job) ||
        !identical(labels[['org.fisheries-workflow.output']], receipt$output)) stop('Refusing to stop a container outside this local job')
    runtime_checked('docker', c('rm', '--force', receipt$container_id), 20)
  }
  invisible(NULL)
}
local_stop <- function(backend) {
  for (id in names(backend$workers)) {
    worker <- backend$workers[[id]]; directory <- local_run_directory(worker$session, id)
    control <- json_read(file.path(directory, 'control.json')); control$cancelled <- TRUE
    json_write(control, file.path(directory, 'control.json'))
    # Interrupt only the coordinator child recorded by this server.
    try(tools::pskill(worker$process$pid, 2L), silent = TRUE)
  }
  deadline <- Sys.time() + 5
  while (length(backend$workers) && Sys.time() < deadline) { local_reap(backend); Sys.sleep(.1) }
  for (id in names(backend$workers)) {
    worker <- backend$workers[[id]]
    output <- file.path(worker$session$directory, 'results')
    try(tools::pskill(worker$process$pid, 15L), silent = TRUE)
    try(local_cleanup_containers(output, backend$config$jobs), silent = TRUE)
  }
  local_reap(backend)
  invisible(NULL)
}
local_serve <- function(backend) {
  if (!requireNamespace('httpuv', quietly = TRUE)) stop('Install the host R package httpuv for the local browser interface')
  server <- httpuv::startServer('127.0.0.1', backend$port, list(call = function(request) local_http(backend, request)))
  on.exit({ httpuv::stopServer(server); local_stop(backend) }, add = TRUE)
  cat('Local run:', paste0(backend$origin, '/'), '\nResults:', backend$directory, '\nPress Ctrl+C to stop.\n')
  repeat { httpuv::service(100); local_reap(backend) }
}
