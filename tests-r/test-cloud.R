#!/usr/bin/env Rscript
# Host fixtures use temporary files and explicit transport/runtime doubles.
script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
setwd(root)
for (name in c("sources", "inputs", "cloud")) source(file.path(root, "R", paste0(name, ".R")))
workflow_require()
passed <- character()
check <- function(name, action) { force(action); passed <<- c(passed, name); cat('PASS ', name, '\n', sep = '') }
reject <- function(action, pattern) {
  failure <- tryCatch({ force(action); NULL }, error = identity)
  stopifnot(inherits(failure, 'error'), grepl(pattern, conditionMessage(failure), fixed = TRUE))
  invisible(failure)
}
request <- '00000000-0000-4000-8000-000000000001'
env <- function(name) switch(name, GITHUB_RUN_ID = '12345', GITHUB_SHA = paste(rep('a', 40), collapse = ''),
  ACTIONS_ID_TOKEN_REQUEST_URL = 'https://identity.invalid/?a=b', ACTIONS_ID_TOKEN_REQUEST_TOKEN = 'private-request-token', '')
make_client <- function(transport, now = function() 1000, sleep = function(value) NULL) {
  client <- new_cloud(request, api = 'https://api.invalid', transport = transport, now = now, sleep = sleep, environ = env)
  client$token <- 'private-runner-token'; client$expires <- 2000
  client
}
ok <- function(value = list(ok = TRUE)) list(status = 200L, value = value)
interrupted <- function() list(status = 0L, value = NULL)
archive <- cloud_base64_encode(charToRaw('archive bytes'))
finish <- list(bundle = archive, checkpoint = archive, state = list(records = list()), result = list(run_id = 'Run 001'), error = NULL, pending_events = list())

check('base64 is canonical and handles sizeable archives', {
  bytes <- as.raw(rep(0:255, 1000))
  stopifnot(identical(cloud_base64(cloud_base64_encode(bytes)), bytes))
  reject(cloud_base64('a==='), 'Invalid preserved archive encoding')
  reject(cloud_base64('YQ=\n'), 'Invalid preserved archive encoding')
})
check('curl hides headers and handles JSON using private files', {
  original <- system2
  observed <- NULL
  system2 <- function(command, args, stdout, stderr, timeout) {
    stopifnot(identical(command, 'curl'), !any(grepl('private', args)))
    path <- gsub("^'|'$", '', args[[2L]])
    observed <<- readLines(path)
    stopifnot(file.info(dirname(path))$mode == as.octmode('0700'), file.info(path)$mode == as.octmode('0600'))
    dest <- sub('^output = "(.*)"$', '\\1', observed[startsWith(observed, 'output = ')])
    writeLines('{"ok":true}', dest)
    '200'
  }
  response <- cloud_http('https://api.invalid', list(Authorization = 'Bearer private-token'), charToRaw('{"a":1}'))
  system2 <- original
  stopifnot(identical(response$value, list(ok = TRUE)), any(grepl('Bearer private-token', observed)), any(grepl('proto = "=https"', observed, fixed = TRUE)))
})
check('OIDC identity audience and refresh stay on the host', {
  calls <- list()
  client <- make_client(function(url, headers = list(), payload = NULL, timeout = 30) {
    calls[[length(calls) + 1L]] <<- list(url = url, headers = headers)
    if (startsWith(url, 'https://identity.invalid')) ok(list(value = 'new-private-token')) else ok(list(settings = list()))
  })
  client$expires <- 0
  cloud_api(client, 'context')
  stopifnot(length(calls) == 2L, grepl('&audience=fisheries-paper-demo', calls[[1L]]$url, fixed = TRUE),
    identical(calls[[2L]]$headers$Authorization, 'Bearer new-private-token'), identical(client$expires, 1240))
})
check('event retries keep the exact operation and payload', {
  payloads <- list(); sleeps <- numeric()
  client <- make_client(function(url, headers = list(), payload = NULL, timeout = 30) {
    payloads[[length(payloads) + 1L]] <<- payload
    if (length(payloads) < 3L) interrupted() else ok()
  }, sleep = function(value) sleeps <<- c(sleeps, value))
  cloud_api(client, 'event', list(event = list(state = 'running')))
  stopifnot(length(payloads) == 3L, identical(payloads[[1L]], payloads[[2L]]), identical(payloads[[2L]], payloads[[3L]]), identical(sleeps, c(.5, 1)))
  body <- jsonlite::fromJSON(rawToChar(payloads[[1L]]), simplifyVector = FALSE)
  stopifnot(grepl('^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$', body$operation_id))
})
check('finish timeout reconciles its bound receipt before resend', {
  paths <- character(); payload_body <- NULL
  client <- make_client(function(url, headers = list(), payload = NULL, timeout = 30) {
    paths <<- c(paths, sub('.*?/runner/', '', url))
    if (grepl('/finish-receipt?', url, fixed = TRUE)) {
      receipt <- c(cloud_binding(client, payload_body), list(operation_id = payload_body$operation_id, payload_hash = paste(rep('b', 64), collapse = '')))
      return(ok(list(receipt = receipt)))
    }
    stopifnot(timeout == 120)
    payload_body <<- jsonlite::fromJSON(rawToChar(payload), simplifyVector = FALSE)
    interrupted()
  })
  stopifnot(isTRUE(cloud_api(client, 'finish', finish)$ok), length(paths) == 2L, startsWith(paths[[2L]], 'finish-receipt?'))
})
check('receipt miss precedes a resend with original finish bytes', {
  calls <- character(); payloads <- list()
  client <- make_client(function(url, headers = list(), payload = NULL, timeout = 30) {
    if (grepl('/finish-receipt?', url, fixed = TRUE)) { calls <<- c(calls, 'receipt'); return(list(status = 404L, value = NULL)) }
    calls <<- c(calls, 'finish'); payloads[[length(payloads) + 1L]] <<- payload
    if (length(payloads) == 1L) interrupted() else ok()
  })
  cloud_api(client, 'finish', finish)
  stopifnot(identical(calls, c('finish', 'receipt', 'finish')), identical(payloads[[1L]], payloads[[2L]]))
})
check('mismatched receipt is rejected without resending', {
  writes <- 0L
  client <- make_client(function(url, headers = list(), payload = NULL, timeout = 30) {
    if (grepl('/finish-receipt?', url, fixed = TRUE)) return(ok(list(receipt = list(status = 'complete'))))
    writes <<- writes + 1L; interrupted()
  })
  reject(cloud_api(client, 'finish', finish), 'original finish receipt did not match')
  stopifnot(writes == 1L)
})
check('failed finish binding permits a null result', {
  body <- finish; body$error <- 'calculation failed'; body$result <- NULL
  binding <- cloud_binding(make_client(function(...) ok()), body)
  stopifnot(identical(binding$status, 'failed'), 'run_id' %in% names(binding), is.null(binding$run_id))
})
check('permanent rejection stops and identity errors are redacted', {
  attempts <- 0L
  client <- make_client(function(...) { attempts <<- attempts + 1L; list(status = 400L, value = list(error = 'bad input')) })
  reject(cloud_api(client, 'context'), 'HTTP 400: bad input'); stopifnot(attempts == 1L)
  client$expires <- 0
  client$transport <- function(...) list(status = 403L, value = list(error = 'private identity detail'))
  failure <- reject(cloud_api(client, 'context'), 'Runner identity request failed.')
  stopifnot(!grepl('private', conditionMessage(failure)))
})
check('pending events preserve order and immutable snapshots', {
  clock <- 1000; available <- FALSE; received <- list()
  client <- make_client(function(url, headers = list(), payload = NULL, timeout = 30) {
    if (!available) return(interrupted())
    received[[length(received) + 1L]] <<- jsonlite::fromJSON(rawToChar(payload), simplifyVector = FALSE)
    ok()
  }, now = function() clock)
  queue <- new_event_delivery(client, tempfile('queue-'))
  body <- list(event = list(state = 'running', message = 'first'))
  cloud_publish(queue, body); body$event$message <- 'changed'
  cloud_publish(queue, list(event = list(state = 'complete', message = 'second')))
  stopifnot(length(cloud_pending(queue)) == 2L)
  available <- TRUE; clock <- 1031; cloud_flush(queue)
  stopifnot(length(received) == 2L, identical(received[[1L]]$event$message, 'first'), identical(received[[2L]]$event$message, 'second'), !length(cloud_pending(queue)))
})
check('parent and forked child share one ordered queue', {
  directory <- tempfile('shared-'); dir.create(directory)
  log <- file.path(directory, 'delivered')
  client <- make_client(function(url, headers = list(), payload = NULL, timeout = 30) {
    value <- jsonlite::fromJSON(rawToChar(payload), simplifyVector = FALSE)
    cat(value$event$message, '\n', file = log, append = TRUE, sep = ''); ok()
  })
  queue <- new_event_delivery(client, file.path(directory, 'queue'))
  child <- parallel::mcparallel({ cloud_publish(queue, list(event = list(state = 'running', message = 'child'))); TRUE }, mc.set.seed = FALSE)
  cloud_publish(queue, list(event = list(state = 'running', message = 'parent')))
  stopifnot(isTRUE(parallel::mccollect(child)[[1L]]), setequal(readLines(log), c('child', 'parent')), !length(cloud_pending(queue)))
})
check('checkpoint roundtrip preserves bytes and hidden files', {
  directory <- tempfile('checkpoint-'); dir.create(directory)
  dir.create(file.path(directory, 'job')); writeBin(as.raw(0:255), file.path(directory, 'job/output.bin'))
  writeLines('state', file.path(directory, '.state'))
  encoded <- cloud_checkpoint(directory); restored <- tempfile('restored-')
  cloud_restore(encoded, restored)
  stopifnot(identical(cloud_bytes(file.path(restored, 'job/output.bin')), as.raw(0:255)), file.exists(file.path(restored, '.state')))
})
check('ZIP traversal is rejected and ZIP symlinks become plain bytes', {
  directory <- tempfile('zip-'); dir.create(directory); dir.create(file.path(directory, 'child'))
  writeLines('outside', file.path(directory, 'outside'))
  previous <- setwd(file.path(directory, 'child'))
  zip <- tempfile(fileext = '.zip'); stopifnot(utils::zip(zip, '../outside', flags = '-q') == 0L)
  setwd(previous)
  reject(cloud_restore(cloud_base64_encode(cloud_bytes(zip)), tempfile('bad-')), 'Unsafe source path')
  stopifnot(file.symlink(file.path(directory, 'outside'), file.path(directory, 'link')))
  previous <- setwd(directory); zip <- tempfile(fileext = '.zip'); stopifnot(utils::zip(zip, 'link', flags = '-qy') == 0L); setwd(previous)
  restored <- tempfile('link-'); cloud_restore(cloud_base64_encode(cloud_bytes(zip)), restored)
  stopifnot(identical(Sys.readlink(file.path(restored, 'link')), ''), identical(rawToChar(cloud_bytes(file.path(restored, 'link'))), file.path(directory, 'outside')))
})
check('manual transfer consumes counters and Connect automatically', {
  controls <- list(list(transfer_count = 0L, connected = FALSE), list(transfer_count = 1L, connected = FALSE), list(transfer_count = 2L, connected = TRUE))
  polls <- 0L; clock <- 1000
  client <- make_client(function(...) { polls <<- polls + 1L; ok(controls[[polls]]) }, now = function() clock, sleep = function(value) clock <<- clock + value)
  queue <- new_event_delivery(client, tempfile('transfer-'))
  first <- cloud_handover(client, queue, 0L); second <- cloud_handover(client, queue, first$transfer_count)
  stopifnot(identical(first, list(transfer_count = 1L, connected = FALSE)), identical(second, list(transfer_count = 2L, connected = TRUE)), polls == 3L)
  reject(cloud_handover(client, queue, 2L, timeout = 0), 'three minutes')
})
# Callback integration uses an explicit workflow and packaging double.
check('hosted callbacks adopt forked acknowledgements and retain final custody', {
  fake_root <- tempfile('root-'); dir.create(fake_root)
  options(workflow.root = fake_root)
  dir.create(file.path(fake_root, 'scripts'))
  writeLines("release_saved_bundle <- function(archive, destination, version) { if (!file.copy(archive, destination)) stop('Fixture packaging failed') }",
    file.path(fake_root, 'scripts/release.R'))
  json_write(list(version = '0.0.0-test'), file.path(fake_root, 'build-info.json'))
  context <- list(id = request, checkpoint = NULL, settings = list(last_year = 2021L, mse = TRUE), handover = 'manual',
    commit_sha = env('GITHUB_SHA'), github_run = env('GITHUB_RUN_ID'), start_job = 'submission', scope = 'workflow')
  finished <- NULL; counter_log <- file.path(fake_root, 'counters')
  client <- make_client(function(url, headers = list(), payload = NULL, timeout = 30) {
    if (grepl('/context?', url, fixed = TRUE)) return(ok(context))
    if (grepl('/data?', url, fixed = TRUE)) return(ok(list(sets = list(), catch = list())))
    if (grepl('/control?', url, fixed = TRUE)) {
      count <- if (file.exists(counter_log)) length(readLines(counter_log)) + 1L else 1L
      cat(count, '\n', file = counter_log, append = TRUE, sep = '')
      return(ok(list(transfer_count = count, connected = count == 2L)))
    }
    body <- jsonlite::fromJSON(rawToChar(payload), simplifyVector = FALSE)
    if (grepl('/finish?', url, fixed = TRUE)) finished <<- body
    if (identical(body$event$state, 'handover')) cat('event:', body$event$transfer_count, '\n', file = file.path(fake_root, 'events'), append = TRUE, sep = '')
    ok()
  })
  new_workflow <- function(output, settings, notify, handover, execution, source_lock) {
    stopifnot(isTRUE(settings$mse), !anyDuplicated(names(settings)))
    dir.create(output, recursive = TRUE, showWarnings = FALSE)
    e <- new.env(); e$output <- output; e$notify <- notify; e$handover <- handover; e$execution <- execution; e$handover_state <- list(transfer_count = 99L)
    e
  }
  workflow_state <- function(runner) list(schema_version = 2L, records = list(job = list(run_id = 'Run 001')), handover_state = runner$handover_state, execution = runner$execution)
  workflow_run <- function(runner, start, scope) {
    runner$notify(list(state = 'plan'), workflow_state(runner), runner$output)
    for (i in 1:2) {
      runner$notify(list(state = 'handover', job = 'job'), workflow_state(runner), runner$output)
      child <- parallel::mcparallel(runner$handover('boundary', 'job'), mc.set.seed = FALSE)
      runner$handover_state <- parallel::mccollect(child)[[1L]]
      runner$notify(list(state = 'received', job = 'job'), workflow_state(runner), runner$output)
    }
    folder <- file.path(runner$output, 'job'); dir.create(folder)
    writeLines('<p>saved output</p>', file.path(folder, 'report.html')); writeBin(charToRaw('%PDF-test'), file.path(folder, 'report.pdf'))
    json_write(list(answer = 42), file.path(folder, 'output.json'))
    json_write(workflow_state(runner), file.path(runner$output, 'state.json'))
    runner$notify(list(state = 'complete', job = 'job'), workflow_state(runner), runner$output)
    list(run_id = 'Run 001')
  }
  workflow_bundle <- function(runner, path) writeBin(charToRaw('mock workflow archive'), path)
  cloud_run(client, file.path(fake_root, 'results'))
  stopifnot(identical(readLines(file.path(fake_root, 'events')), c('event:0', 'event:1')), identical(finished$result$run_id, 'Run 001'),
    !length(finished$pending_events), !grepl('private-', json_encode(finished)), isTRUE(finished$state$handover_state$connected),
    identical(finished$state$handover_state$transfer_count, 2L))
  restored <- tempfile('finish-checkpoint-'); cloud_restore(finished$checkpoint, restored)
  stopifnot(file.exists(file.path(restored, 'state.json')))
})
cat(length(passed), 'hosted transport and custody fixtures passed. No external service or model used.\n')
