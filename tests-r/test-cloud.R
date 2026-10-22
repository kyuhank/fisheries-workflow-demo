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
checkpoint_member <- function(bytes) list(sha256 = digest::digest(bytes, algo = 'sha256', serialize = FALSE),
  content_base64 = cloud_base64_encode(bytes))
checkpoint_map <- function(value) cloud_base64_encode(c(cloud_checkpoint_magic(), memCompress(charToRaw(json_encode(value)), 'bzip2')))
checkpoint_text <- function(value) cloud_base64_encode(c(cloud_checkpoint_magic(), memCompress(charToRaw(value), 'bzip2')))
with_checkpoint_limits <- function(changes, action) {
  original <- cloud_checkpoint_limits
  limits <- modifyList(original(), changes)
  cloud_checkpoint_limits <<- function() limits
  on.exit(cloud_checkpoint_limits <<- original, add = TRUE)
  force(action)
}
check('solid checkpoint preserves bytes, empty files and hidden files without scratch caches', {
  directory <- tempfile('checkpoint-'); dir.create(directory)
  dir.create(file.path(directory, 'job')); writeBin(as.raw(0:255), file.path(directory, 'job/output.bin'))
  writeBin(raw(), file.path(directory, 'empty'))
  writeLines('state', file.path(directory, '.state'))
  writeBin(charToRaw('First line\n표준화 café\r\n'), file.path(directory, 'utf8.txt'))
  writeBin(as.raw(c(65, 0, 66)), file.path(directory, 'nul.bin'))
  writeBin(as.raw(c(255, 254, 128)), file.path(directory, 'nonutf8.bin'))
  dir.create(file.path(directory, '.quarto')); writeLines('scratch', file.path(directory, '.quarto/cache'))
  encoded <- cloud_checkpoint(directory); restored <- tempfile('restored-')
  stopifnot(identical(head(cloud_base64(encoded), length(cloud_checkpoint_magic())), cloud_checkpoint_magic()))
  cloud_restore(encoded, restored)
  stopifnot(identical(cloud_bytes(file.path(restored, 'job/output.bin')), as.raw(0:255)),
    file.exists(file.path(restored, '.state')), file.info(file.path(restored, 'empty'))$size == 0,
    !dir.exists(file.path(restored, '.quarto')))
  for (name in c('utf8.txt', 'nul.bin', 'nonutf8.bin')) stopifnot(identical(cloud_bytes(file.path(restored, name)), cloud_bytes(file.path(directory, name))))
  decoded <- cloud_checkpoint_json(cloud_base64(encoded)[-seq_along(cloud_checkpoint_magic())], cloud_checkpoint_limits()$json)
  stopifnot('content_utf8' %in% names(decoded[['utf8.txt']]), 'content_base64' %in% names(decoded[['nul.bin']]),
    'content_base64' %in% names(decoded[['nonutf8.bin']]))
})
check('completed checkpoints preserve recorded artifacts and omit calculation scratch files', {
  directory <- tempfile('recorded-checkpoint-'); dir.create(directory); dir.create(file.path(directory, 'job'))
  writeLines('saved output', file.path(directory, 'job/output.json'))
  writeBin(as.raw(c(1, 0, 2)), file.path(directory, 'job/snapshot.sqlite'))
  writeLines('temporary context', file.path(directory, 'job/context.json'))
  dir.create(file.path(directory, '.runtime')); writeLines('cached runtime', file.path(directory, '.runtime/info.json'))
  outputs <- list('output.json' = file_sha256(file.path(directory, 'job/output.json')),
    'snapshot.sqlite' = file_sha256(file.path(directory, 'job/snapshot.sqlite')))
  record <- list(run_id = 'Run 001', outputs = outputs)
  json_write(record, file.path(directory, 'job/record.json'))
  json_write(list(schema_version = 2L, records = list(job = record)), file.path(directory, 'state.json'))
  restored <- tempfile('recorded-restored-'); cloud_restore(cloud_checkpoint(directory), restored)
  stopifnot(setequal(list.files(restored, recursive = TRUE, all.files = TRUE, no.. = TRUE),
    c('state.json', 'job/record.json', 'job/output.json', 'job/snapshot.sqlite')),
    identical(cloud_bytes(file.path(directory, 'job/snapshot.sqlite')), cloud_bytes(file.path(restored, 'job/snapshot.sqlite'))))
  writeLines('changed output', file.path(directory, 'job/output.json'))
  reject(cloud_checkpoint(directory), 'recorded file checksum mismatch')
})
check('checkpoint validates every hash, encoding and path before writing files', {
  good <- checkpoint_member(charToRaw('saved output'))
  bad <- good; bad$sha256 <- paste(rep('0', 64), collapse = '')
  target <- tempfile('bad-checkpoint-')
  reject(cloud_restore(checkpoint_map(list(first = good, second = bad)), target), 'file checksum mismatch')
  stopifnot(!dir.exists(target))
  bad <- good; bad$content_base64 <- 'Zh=='
  reject(cloud_restore(checkpoint_map(list(bad = bad)), target), 'Invalid preserved archive encoding')
  for (name in c('../outside', '/outside', 'C:/outside', 'job/../outside', 'job\\outside', 'job//outside')) {
    value <- setNames(list(good), name)
    reject(cloud_restore(checkpoint_map(value), target), 'Unsafe source path')
  }
  reject(cloud_restore(checkpoint_map(setNames(list(good, good), c('job', 'job/output'))), target), 'Conflicting preserved checkpoint paths')
  stopifnot(!length(list.files(target, all.files = TRUE, no.. = TRUE)))
  dir.create(file.path(target, 'existing'))
  reject(cloud_restore(checkpoint_map(list(existing = good)), target), 'Conflicting preserved checkpoint paths')
  outside <- tempfile('checkpoint-outside-'); dir.create(outside)
  stopifnot(file.symlink(outside, file.path(target, 'linked')))
  reject(cloud_restore(checkpoint_map(list(first = good, 'linked/output' = good)), target), 'Symlink source path')
  stopifnot(!file.exists(file.path(target, 'first')), !length(list.files(outside)))
})
check('checkpoint rejects duplicate JSON fields and malformed compressed content', {
  good <- checkpoint_member(charToRaw('value')); member <- json_encode(good)
  reject(cloud_restore(checkpoint_text(paste0('{"job":', member, ',"job":', member, '}')), tempfile()), 'Duplicate preserved checkpoint JSON field')
  reject(cloud_restore(checkpoint_text(paste0('{"job":{"sha256":"', good$sha256, '","sha256":"', good$sha256,
    '","content_base64":"', good$content_base64, '"}}')), tempfile()), 'Duplicate preserved checkpoint JSON field')
  reject(cloud_restore(checkpoint_text('{broken'), tempfile()), 'Invalid preserved checkpoint JSON')
  reject(cloud_restore(cloud_base64_encode(c(cloud_checkpoint_magic(), charToRaw('not gzip'))), tempfile()), 'Invalid preserved checkpoint compression')
  bytes <- cloud_base64(checkpoint_map(list(job = good)))
  reject(cloud_restore(cloud_base64_encode(head(bytes, -2L)), tempfile()), 'compression checksum')
  bytes[[length(bytes) - 7L]] <- as.raw(bitwXor(as.integer(bytes[[length(bytes) - 7L]]), 1L))
  reject(cloud_restore(cloud_base64_encode(bytes), tempfile()), 'compression checksum')
})
check('checkpoint enforces compressed, expanded, file-count and file-size bounds', {
  good <- checkpoint_member(charToRaw('value')); encoded <- checkpoint_map(list(first = good, second = good))
  with_checkpoint_limits(list(compressed = 10L), reject(cloud_restore(encoded, tempfile()), 'compressed size limit'))
  with_checkpoint_limits(list(json = 20L), reject(cloud_restore(encoded, tempfile()), 'expanded size limit'))
  with_checkpoint_limits(list(files = 1L), reject(cloud_restore(encoded, tempfile()), 'file count'))
  with_checkpoint_limits(list(file = 2L), reject(cloud_restore(encoded, tempfile()), 'Invalid preserved checkpoint file'))
  with_checkpoint_limits(list(total = 6L), reject(cloud_restore(encoded, tempfile()), 'file size limit'))
  directory <- tempfile('checkpoint-limits-'); dir.create(directory)
  writeLines('value', file.path(directory, 'first')); writeLines('value', file.path(directory, 'second'))
  with_checkpoint_limits(list(files = 1L), reject(cloud_checkpoint(directory), 'file count'))
  with_checkpoint_limits(list(file = 2L), reject(cloud_checkpoint(directory), 'file size limit'))
  with_checkpoint_limits(list(total = 6L), reject(cloud_checkpoint(directory), 'file size limit'))
  with_checkpoint_limits(list(json = 20L), reject(cloud_checkpoint(directory), 'expanded size limit'))
  with_checkpoint_limits(list(compressed = 10L), reject(cloud_checkpoint(directory), 'compressed size limit'))
})
check('previous solid gzip checkpoints remain readable and validate their footer', {
  value <- list(job = checkpoint_member(charToRaw('saved output')))
  bytes <- c(cloud_checkpoint_magic(2L), cloud_checkpoint_gzip(charToRaw(json_encode(value))))
  restored <- tempfile('gzip-restored-'); cloud_restore(cloud_base64_encode(bytes), restored)
  stopifnot(identical(cloud_bytes(file.path(restored, 'job')), charToRaw('saved output')))
  bytes[[length(bytes) - 7L]] <- as.raw(bitwXor(as.integer(bytes[[length(bytes) - 7L]]), 1L))
  reject(cloud_restore(cloud_base64_encode(bytes), tempfile()), 'compression checksum')
  # A forged gzip footer cannot bypass the streaming expanded-size bound.
  bytes[(length(bytes) - 3L):length(bytes)] <- as.raw(c(1, 0, 0, 0))
  with_checkpoint_limits(list(json = 20L), reject(cloud_restore(cloud_base64_encode(bytes), tempfile()), 'expanded size limit'))
})
check('legacy ZIP checkpoints still restore binary and hidden files', {
  directory <- tempfile('legacy-checkpoint-'); dir.create(directory)
  writeBin(as.raw(0:255), file.path(directory, 'binary')); writeLines('state', file.path(directory, '.state'))
  archive <- tempfile(fileext = '.zip'); previous <- setwd(directory)
  stopifnot(utils::zip(archive, files = c('binary', '.state'), flags = '-q') == 0L); setwd(previous)
  restored <- tempfile('legacy-restored-'); cloud_restore(cloud_base64_encode(cloud_bytes(archive)), restored)
  stopifnot(identical(cloud_bytes(file.path(restored, 'binary')), as.raw(0:255)), file.exists(file.path(restored, '.state')))
  with_checkpoint_limits(list(files = 1L), reject(cloud_restore(cloud_base64_encode(cloud_bytes(archive)), tempfile()), 'file count'))
  with_checkpoint_limits(list(file = 2L), reject(cloud_restore(cloud_base64_encode(cloud_bytes(archive)), tempfile()), 'file size limit'))
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
  finished <- NULL; event_bodies <- list(); counter_log <- file.path(fake_root, 'counters')
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
    if (grepl('/event?', url, fixed = TRUE)) event_bodies[[length(event_bodies) + 1L]] <<- body
    if (identical(body$event$state, 'handover')) cat('event:', body$event$transfer_count, '\n', file = file.path(fake_root, 'events'), append = TRUE, sep = '')
    ok()
  })
  new_workflow <- function(output, settings, notify, handover, execution, source_lock) {
    stopifnot(isTRUE(settings$mse), !anyDuplicated(names(settings)))
    dir.create(output, recursive = TRUE, showWarnings = FALSE)
    e <- new.env(); e$output <- output; e$notify <- notify; e$handover <- handover; e$execution <- execution; e$handover_state <- list(transfer_count = 99L)
    e
  }
  workflow_state <- function(runner) list(schema_version = 2L,
    records = list(job = list(run_id = 'Run 001'), retained = list(run_id = 'Run 000', signature = 'original producer')),
    handover_state = runner$handover_state, execution = runner$execution, fixture_padding = strrep('s', 8192L))
  workflow_run <- function(runner, start, scope) {
    runner$notify(list(state = 'plan'), workflow_state(runner), runner$output)
    runner$notify(list(state = 'running', job = 'job'), workflow_state(runner), runner$output)
    runner$notify(list(state = 'activity', activity = 'preparing', job = 'job'), workflow_state(runner), runner$output)
    runner$notify(list(state = 'activity', activity = 'calculating', job = 'job'), workflow_state(runner), runner$output)
    runner$notify(list(state = 'activity', activity = 'rendering', job = 'job'), workflow_state(runner), runner$output)
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
    list(run_id = 'Run 001', records = workflow_state(runner)$records, jobs = list(job = list(title = 'Job')))
  }
  workflow_bundle <- function(runner, path) writeBin(charToRaw('mock workflow archive'), path)
  cloud_run(client, file.path(fake_root, 'results'))
  stopifnot(identical(readLines(file.path(fake_root, 'events')), c('event:0', 'event:1')), identical(finished$result$run_id, 'Run 001'),
    !length(finished$pending_events), !'jobs' %in% names(finished$result), identical(finished$result$records, finished$state$records),
    !grepl('private-', json_encode(finished)), isTRUE(finished$state$handover_state$connected),
    identical(finished$state$handover_state$transfer_count, 2L))
  restored <- tempfile('finish-checkpoint-'); cloud_restore(finished$checkpoint, restored)
  stopifnot(file.exists(file.path(restored, 'state.json')))
})
check('hosted progress keeps ordered transitions without redundant full-state writes', {
  states <- vapply(event_bodies, function(body) body$event$state, character(1))
  stopifnot(identical(states, c('plan', 'running', 'activity', 'handover', 'received', 'handover', 'received', 'complete')),
    identical(event_bodies[[3L]]$event$activity, 'rendering'),
    !any(vapply(event_bodies, function(body) isTRUE(body$event$activity %in% c('preparing', 'calculating')), logical(1))))
  for (body in event_bodies) {
    full <- body$event$state %in% c('plan', 'complete', 'received', 'failed')
    stopifnot(identical('state' %in% names(body), full),
      identical('output' %in% names(body), identical(body$event$state, 'complete')))
    if (!full) stopifnot(nchar(json_encode(body), type = 'bytes') < nchar(json_encode(finished$state), type = 'bytes') / 8)
  }
  operations <- vapply(event_bodies, function(body) body$operation_id, character(1))
  stopifnot(!anyDuplicated(operations), all(grepl('^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$', operations)),
    identical(event_bodies[[4L]]$event$request_id, request), identical(event_bodies[[4L]]$event$transfer_count, 0L),
    identical(event_bodies[[6L]]$event$transfer_count, 1L), identical(event_bodies[[5L]]$state$handover_state$transfer_count, 1L),
    identical(event_bodies[[7L]]$state$handover_state$transfer_count, 2L), isTRUE(event_bodies[[7L]]$state$handover_state$connected))
  published <- event_bodies[[8L]]$output
  stopifnot(identical(published$html, '<p>saved output</p>\n'), identical(cloud_base64(published$pdf_base64), charToRaw('%PDF-test')),
    identical(published$record, finished$state$records$job), identical(published$output, list(answer = 42L)),
    identical(finished$result$records$retained, list(run_id = 'Run 000', signature = 'original producer')))
})
check('hosted failures retain the full state and finish custody', {
  original_run <- workflow_run
  workflow_run <- function(runner, start, scope) {
    json_write(workflow_state(runner), file.path(runner$output, 'state.json'))
    runner$notify(list(state = 'failed', job = 'job', message = 'fixture calculation failed'), workflow_state(runner), runner$output)
    stop('fixture calculation failed')
  }
  client$request <- '00000000-0000-4000-8000-000000000002'; context$id <- client$request
  reject(cloud_run(client, file.path(fake_root, 'failed-results')), 'fixture calculation failed')
  workflow_run <- original_run
  failure <- tail(event_bodies, 1L)[[1L]]
  stopifnot(identical(failure$event$state, 'failed'), identical(failure$state, finished$state), !'output' %in% names(failure),
    identical(finished$error, 'fixture calculation failed'), is.null(finished$result), !length(finished$pending_events))
})
cat(length(passed), 'hosted transport and custody fixtures passed. No external service or model used.\n')
