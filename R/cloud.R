# Hosted transport stays on the host; analysis containers receive no credentials.
cloud_uuid <- function() {
  con <- file("/dev/urandom", "rb", raw = TRUE); on.exit(close(con), add = TRUE)
  bytes <- as.integer(readBin(con, "raw", 16L))
  if (length(bytes) != 16L) stop("Cannot create an operation identifier")
  bytes[[7L]] <- bitwOr(bitwAnd(bytes[[7L]], 15L), 64L)
  bytes[[9L]] <- bitwOr(bitwAnd(bytes[[9L]], 63L), 128L)
  hex <- paste(sprintf("%02x", bytes), collapse = "")
  paste(substring(hex, 1L, 8L), substring(hex, 9L, 12L), substring(hex, 13L, 16L),
        substring(hex, 17L, 20L), substring(hex, 21L, 32L), sep = "-")
}
cloud_temporary <- function(message) stop(structure(list(message = message, call = NULL),
  class = c("cloud_temporary", "error", "condition")))
cloud_copy <- function(value) unserialize(serialize(value, NULL))
cloud_bytes <- function(path) readBin(path, "raw", n = file.info(path)$size)
cloud_base64_encode <- function(bytes) gsub("\n", "", jsonlite::base64_enc(bytes), fixed = TRUE)
cloud_base64 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || nchar(value) %% 4L ||
      !grepl("^[A-Za-z0-9+/]*={0,2}$", value))
    stop("Invalid preserved archive encoding")
  bytes <- jsonlite::base64_dec(value)
  if (!identical(cloud_base64_encode(bytes), value)) stop("Invalid preserved archive encoding")
  bytes
}

# Secrets go into a private curl configuration, never command arguments or logs.
cloud_http <- function(url, headers = list(), payload = NULL, timeout = 30) {
  directory <- tempfile("paper-http-"); dir.create(directory, mode = "0700")
  on.exit(unlink(directory, recursive = TRUE), add = TRUE)
  quote_config <- function(value) {
    if (grepl("[\r\n]", value)) stop("Invalid HTTP field")
    paste0('"', gsub('"', '\\"', gsub('\\', '\\\\', value, fixed = TRUE), fixed = TRUE), '"')
  }
  response <- file.path(directory, "response"); config <- file.path(directory, "curl.conf")
  fields <- c("silent", "show-error", "proto = \"=https\"", "connect-timeout = 30",
    paste0("max-time = ", as.integer(timeout)), paste0("url = ", quote_config(url)),
    paste0("output = ", quote_config(response)), "write-out = \"%{http_code}\"")
  for (name in names(headers)) fields <- c(fields, paste0("header = ", quote_config(paste0(name, ": ", headers[[name]]))))
  if (!is.null(payload)) {
    body <- file.path(directory, "body"); writeBin(payload, body)
    fields <- c(fields, "request = \"POST\"", paste0("data-binary = ", quote_config(paste0("@", body))))
  }
  writeLines(fields, config); Sys.chmod(config, "0600")
  status <- suppressWarnings(system2("curl", c("--config", shQuote(config)), stdout = TRUE,
                                    stderr = file.path(directory, "curl-error"), timeout = timeout + 5L))
  if (!is.null(attr(status, "status"))) return(list(status = 0L, value = NULL))
  code <- suppressWarnings(as.integer(paste(status, collapse = "")))
  value <- tryCatch(jsonlite::fromJSON(response, simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(value)) value <- NULL
  list(status = code, value = value)
}
new_cloud <- function(request = Sys.getenv("PAPER_REQUEST_ID"),
  api = "https://gvunwnpsfmylmqfqowzp.supabase.co/functions/v1/paper-api",
  transport = cloud_http, now = function() as.numeric(Sys.time()), sleep = Sys.sleep,
  environ = Sys.getenv) {
  if (!grepl("^[a-fA-F0-9]{8}(-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$", request)) stop("Invalid demonstration request")
  client <- new.env(parent = emptyenv())
  client$request <- tolower(request); client$api <- api; client$transport <- transport
  client$now <- now; client$sleep <- sleep; client$environ <- environ
  client$token <- ""; client$expires <- 0
  client
}
cloud_binding <- function(client, body) {
  run <- client$environ("GITHUB_RUN_ID"); commit <- client$environ("GITHUB_SHA")
  error <- if (is.null(body$error) || identical(body$error, "")) NULL else body$error
  run_id <- if (is.list(body$result)) body$result$run_id else NULL
  if (!grepl("^[0-9]{1,20}$", run) || !grepl("^[a-f0-9]{40}$", commit) ||
      (is.null(error) && (!is.character(run_id) || length(run_id) != 1L || !nzchar(run_id)))) return(NULL)
  hashes <- tryCatch(lapply(body[c("bundle", "checkpoint")], function(value)
    digest::digest(cloud_base64(value), algo = "sha256", serialize = FALSE)), error = function(error) NULL)
  if (is.null(hashes) || length(hashes) != 2L) return(NULL)
  list(request_id = client$request, github_run = run, commit_sha = commit,
       status = if (is.null(error)) "complete" else "failed", error = error, run_id = run_id,
       bundle_sha256 = hashes$bundle, checkpoint_sha256 = hashes$checkpoint)
}
cloud_receipt <- function(client, operation, expected, wire_hash) {
  url <- paste0(client$api, "/runner/finish-receipt?request=", client$request, "&operation_id=", operation)
  response <- client$transport(url, list(Authorization = paste("Bearer", client$token)), timeout = 30)
  if (is.na(response$status) || response$status %in% c(0L, 404L, 408L, 429L, 500L, 502L, 503L, 504L)) return(NULL)
  if (response$status < 200L || response$status >= 300L) stop("finish-receipt: HTTP ", response$status, ": Receipt lookup rejected.")
  receipt <- response$value$receipt
  if (is.null(receipt)) return(NULL)
  hash <- function(value) is.character(value) && length(value) == 1L && grepl("^[a-f0-9]{64}$", value)
  if (!is.list(receipt) || !all(names(expected) %in% names(receipt)) ||
      !identical(receipt$operation_id, operation) || !hash(receipt$payload_hash) ||
      !hash(receipt$bundle_sha256) || !hash(receipt$checkpoint_sha256) ||
      !all(vapply(names(expected), function(name) identical(receipt[[name]], expected[[name]]), logical(1))))
    stop("finish-receipt: The original finish receipt did not match.")
  cat("Finish acknowledgement reconciled: ", json_encode(c(expected, list(operation_id = operation,
    payload_hash = receipt$payload_hash, finish_body_sha256 = wire_hash))), "\n", sep = "")
  list(ok = TRUE)
}
cloud_api <- function(client, path, body = NULL) {
  if (!path %in% c("context", "data", "control", "event", "finish")) stop("Unknown runner operation")
  if (!is.null(body) && path %in% c("event", "finish") && is.null(body$operation_id)) body$operation_id <- cloud_uuid()
  payload <- if (is.null(body)) NULL else charToRaw(json_encode(body))
  if (!is.null(payload) && length(payload) > 16000000L) stop("Runner output exceeds the service's preserved payload limit")
  expected <- if (path == "finish") cloud_binding(client, body) else NULL
  wire_hash <- if (is.null(expected)) NULL else digest::digest(payload, algo = "sha256", serialize = FALSE)
  for (attempt in 0:2) {
    identity <- FALSE; response <- NULL
    if (client$now() >= client$expires) {
      identity <- TRUE
      url <- client$environ("ACTIONS_ID_TOKEN_REQUEST_URL")
      token <- client$environ("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
      if (!nzchar(url) || !nzchar(token)) stop("GitHub runner identity is unavailable")
      url <- paste0(url, if (grepl("?", url, fixed = TRUE)) "&" else "?", "audience=fisheries-paper-demo")
      response <- client$transport(url, list(Authorization = paste("Bearer", token)), timeout = 30)
      if (!is.na(response$status) && response$status >= 200L && response$status < 300L &&
          is.character(response$value$value) && length(response$value$value) == 1L && nzchar(response$value$value)) {
        client$token <- response$value$value; client$expires <- client$now() + 240; identity <- FALSE
      }
    }
    if (!identity) response <- client$transport(paste0(client$api, "/runner/", path, "?request=", client$request),
      list(Authorization = paste("Bearer", client$token), "Content-Type" = "application/json"), payload,
      timeout = if (path == "finish") 120 else 30)
    code <- response$status
    if (!is.na(code) && code >= 200L && code < 300L && is.list(response$value) && !identity) return(response$value)
    message <- response$value$error %||% "Request rejected."
    if (!is.character(message) || length(message) != 1L) message <- "Request rejected."
    legacy <- message %in% c("The database connection was interrupted.",
      paste0("The database request could not be completed (HTTP ", c(429, 500, 502, 503, 504), ")."))
    transient <- is.na(code) || code == 0L || code %in% c(408L, 429L, 500L, 502L, 503L, 504L) ||
      (!identity && code == 400L && legacy) || (code >= 200L && code < 300L)
    failure <- if (is.na(code) || code == 0L || (code >= 200L && code < 300L)) paste0(path, ": The service connection was interrupted.")
      else paste0(path, ": HTTP ", code, ": ", if (identity) "Runner identity request failed." else substr(message, 1L, 240L))
    if (!isTRUE(transient)) stop(failure)
    # An uncertain finish is read back using its original operation before any resend.
    if (path == "finish" && !identity && !is.null(expected)) {
      acknowledged <- cloud_receipt(client, body$operation_id, expected, wire_hash)
      if (!is.null(acknowledged)) return(acknowledged)
    }
    if (attempt == 2L) cloud_temporary(failure)
    client$sleep(0.5 * 2^attempt)
  }
}

# A directory lock serialises parent status updates and forked handover polling.
new_event_delivery <- function(client, directory) {
  dir.create(directory, recursive = TRUE, showWarnings = FALSE, mode = "0700")
  delivery <- list(client = client, path = file.path(directory, "events.json"), lock = file.path(directory, "events.lock"))
  if (!file.exists(delivery$path)) json_write(list(pending = list(), retry_at = 0), delivery$path)
  delivery
}
cloud_queue_lock <- function(delivery, action) {
  deadline <- delivery$client$now() + 240
  while (!dir.create(delivery$lock, showWarnings = FALSE)) {
    if (delivery$client$now() >= deadline) stop("Timed out waiting for status delivery")
    delivery$client$sleep(0.05)
  }
  on.exit(unlink(delivery$lock, recursive = TRUE), add = TRUE)
  action()
}
cloud_flush_locked <- function(delivery, queue, required = FALSE) {
  if (!required && delivery$client$now() < queue$retry_at) return(invisible(NULL))
  while (length(queue$pending)) {
    failure <- tryCatch({ cloud_api(delivery$client, "event", queue$pending[[1L]]); NULL }, cloud_temporary = identity)
    if (!is.null(failure)) {
      queue$retry_at <- delivery$client$now() + 30; json_write(queue, delivery$path)
      if (required) stop(failure)
      cat("Status delivery delayed; calculations and records continue locally.\n")
      return(invisible(NULL))
    }
    queue$pending <- queue$pending[-1L]; queue$retry_at <- 0; json_write(queue, delivery$path)
  }
  invisible(NULL)
}
cloud_publish <- function(delivery, body) cloud_queue_lock(delivery, function() {
  queue <- json_read(delivery$path)
  if (is.null(body$operation_id)) body$operation_id <- cloud_uuid()
  queue$pending[[length(queue$pending) + 1L]] <- cloud_copy(body)
  json_write(queue, delivery$path); cloud_flush_locked(delivery, queue)
})
cloud_flush <- function(delivery, required = FALSE) cloud_queue_lock(delivery, function()
  cloud_flush_locked(delivery, json_read(delivery$path), required))
cloud_pending <- function(delivery) cloud_queue_lock(delivery, function() json_read(delivery$path)$pending)

# The checkpoint is opaque to the service. One compressed stream avoids repeating
# the same analysis records across individually compressed files.
cloud_checkpoint_limits <- function() list(compressed = 12000000L, json = 96000000L,
  files = 4096L, file = 8000000L, total = 64000000L)
cloud_checkpoint_magic <- function(version = 3L) {
  if (!version %in% c(2L, 3L)) stop("Unknown preserved checkpoint version")
  charToRaw(paste0("FWCP", version, "\n"))
}
cloud_checkpoint_name <- function(name) {
  if (!is.character(name) || length(name) != 1L || is.na(name) || !nzchar(name) ||
      grepl("^[A-Za-z]:|^/|\\\\|//|/$|[[:cntrl:]]", name) ||
      any(strsplit(name, "/", fixed = TRUE)[[1L]] %in% c(".", "..", "")))
    stop("Unsafe source path in preserved checkpoint")
  invisible(name)
}
cloud_checkpoint_gzip <- function(bytes) {
  path <- tempfile(fileext = ".gz"); on.exit(unlink(path), add = TRUE)
  connection <- gzfile(path, "wb")
  tryCatch(writeBin(bytes, connection), finally = close(connection))
  cloud_bytes(path)
}
cloud_checkpoint_json <- function(bytes, limit, version = 3L) {
  if (version == 3L) {
    if (length(bytes) < 14L || !identical(bytes[1:4], charToRaw("BZh9")))
      stop("Invalid preserved checkpoint compression")
    path <- tempfile(fileext = ".bz2"); on.exit(unlink(path), add = TRUE)
    writeBin(bytes, path); connection <- bzfile(path, "rb")
    expanded <- tryCatch(readBin(connection, "raw", n = limit + 1L),
      error = function(error) stop("Invalid preserved checkpoint compression"),
      finally = close(connection))
    if (length(expanded) > limit) stop("Preserved checkpoint exceeds the expanded size limit")
    # R's bzfile may silently return partial data after a truncated footer.
    # FWCP3 uses the canonical BZip stream made by memCompress at level nine.
    if (!identical(memCompress(expanded, "bzip2"), bytes))
      stop("Invalid preserved checkpoint compression checksum")
  } else {
    if (length(bytes) < 18L || !identical(bytes[1:4], as.raw(c(31, 139, 8, 0))))
      stop("Invalid preserved checkpoint compression")
    # gzcon can return truncated bytes after a CRC failure; check its footer too.
    footer <- tail(bytes, 8L)
    size <- sum(as.integer(footer[5:8]) * 256^(0:3))
    if (size > limit) stop("Preserved checkpoint exceeds the expanded size limit")
    connection <- gzcon(rawConnection(bytes, "rb"), allowNonCompressed = FALSE)
    expanded <- tryCatch(readBin(connection, "raw", n = limit + 1L),
      error = function(error) stop("Invalid preserved checkpoint compression"),
      finally = close(connection))
    if (length(expanded) > limit) stop("Preserved checkpoint exceeds the expanded size limit")
    crc <- paste(sprintf("%02x", rev(as.integer(footer[1:4]))), collapse = "")
    if (length(expanded) != size || !identical(digest::digest(expanded, algo = "crc32", serialize = FALSE), crc))
      stop("Invalid preserved checkpoint compression checksum")
  }
  value <- tryCatch(jsonlite::fromJSON(rawToChar(expanded), simplifyVector = FALSE),
    error = function(error) stop("Invalid preserved checkpoint JSON"))
  unique_fields <- function(item) {
    if (is.list(item)) {
      if (!is.null(names(item)) && anyDuplicated(names(item))) stop("Duplicate preserved checkpoint JSON field")
      invisible(lapply(item, unique_fields))
    }
  }
  unique_fields(value)
  value
}
cloud_restore <- function(encoded, directory) {
  if (is.null(encoded) || identical(encoded, "")) return(invisible(NULL))
  limits <- cloud_checkpoint_limits(); magic <- cloud_checkpoint_magic()
  if (!is.character(encoded) || length(encoded) != 1L || is.na(encoded) ||
      nchar(encoded, type = "bytes") > 4 * ceiling((limits$compressed + length(magic)) / 3))
    stop("Preserved checkpoint exceeds the compressed size limit")
  bytes <- cloud_base64(encoded)
  if (length(bytes) > limits$compressed + length(magic)) stop("Preserved checkpoint exceeds the compressed size limit")
  files <- list()
  version <- if (length(bytes) >= length(magic) && identical(head(bytes, length(magic)), magic)) 3L
    else if (length(bytes) >= length(magic) && identical(head(bytes, length(magic)), cloud_checkpoint_magic(2L))) 2L
    else NULL
  if (!is.null(version)) {
    compressed <- bytes[-seq_along(magic)]
    if (length(compressed) > limits$compressed) stop("Preserved checkpoint exceeds the compressed size limit")
    members <- cloud_checkpoint_json(compressed, limits$json, version)
    if (!is.list(members) || is.null(names(members)) || !length(members) || length(members) > limits$files)
      stop("Invalid preserved checkpoint file count")
    total <- 0
    for (name in names(members)) {
      cloud_checkpoint_name(name)
      member <- members[[name]]
      encoding <- setdiff(names(member), "sha256")
      if (!is.list(member) || length(member) != 2L || length(encoding) != 1L ||
          !encoding %in% c("content_base64", if (version == 3L) "content_utf8") ||
          !is.character(member$sha256) || length(member$sha256) != 1L || is.na(member$sha256) ||
          !grepl("^[a-f0-9]{64}$", member$sha256) || !is.character(member[[encoding]]) ||
          length(member[[encoding]]) != 1L || is.na(member[[encoding]]))
        stop("Invalid preserved checkpoint file")
      value <- member[[encoding]]
      if (encoding == "content_base64") {
        if (nchar(value, type = "bytes") > 4 * ceiling(limits$file / 3)) stop("Invalid preserved checkpoint file")
        content <- cloud_base64(value)
      } else {
        if (!isTRUE(validUTF8(value)) || nchar(value, type = "bytes") > limits$file)
          stop("Invalid preserved checkpoint file")
        content <- charToRaw(enc2utf8(value))
      }
      total <- total + length(content)
      if (length(content) > limits$file || total > limits$total) stop("Preserved checkpoint exceeds the file size limit")
      if (!identical(digest::digest(content, algo = "sha256", serialize = FALSE), member$sha256))
        stop("Preserved checkpoint file checksum mismatch")
      files[[name]] <- content
    }
  } else {
    # Earlier checkpoints used ZIP. Read each member as bytes, never as a link.
    if (length(bytes) > limits$compressed) stop("Preserved checkpoint exceeds the compressed size limit")
    archive <- tempfile(fileext = ".zip"); writeBin(bytes, archive)
    on.exit(unlink(archive), add = TRUE)
    members <- utils::unzip(archive, list = TRUE)
    if (!nrow(members) || nrow(members) > limits$files) stop("Invalid preserved checkpoint file count")
    if (anyDuplicated(members$Name)) stop("Duplicate preserved archive member")
    if (any(!is.finite(members$Length) | members$Length < 0 | members$Length > limits$file) ||
        sum(members$Length) > limits$total) stop("Preserved checkpoint exceeds the file size limit")
    for (i in seq_len(nrow(members))) {
      name <- members$Name[[i]]; is_directory <- endsWith(name, "/")
      if (is_directory) name <- substring(name, 1L, nchar(name) - 1L)
      cloud_checkpoint_name(name)
      if (is_directory) next
      connection <- unz(archive, members$Name[[i]], open = "rb")
      content <- tryCatch(readBin(connection, "raw", n = members$Length[[i]] + 1L), finally = close(connection))
      if (length(content) != members$Length[[i]]) stop("Invalid preserved file length")
      files[[name]] <- content
    }
  }
  # Validate every path before restoring any file, including existing symlinks.
  dir.create(directory, recursive = TRUE, showWarnings = FALSE)
  for (name in names(files)) {
    parts <- strsplit(name, "/", fixed = TRUE)[[1L]]
    if (length(parts) > 1L && any(vapply(seq_len(length(parts) - 1L), function(i)
        paste(parts[seq_len(i)], collapse = "/") %in% names(files), logical(1))))
      stop("Conflicting preserved checkpoint paths")
  }
  paths <- lapply(names(files), function(name) {
    path <- source_path(directory, name, exists = FALSE)
    parent <- dirname(path)
    while (!identical(parent, directory) && !dir.exists(parent)) {
      if (file.exists(parent)) stop("Conflicting preserved checkpoint paths")
      parent <- dirname(parent)
    }
    if (dir.exists(path)) stop("Conflicting preserved checkpoint paths")
    path
  })
  for (i in seq_along(files)) {
    dir.create(dirname(paths[[i]]), recursive = TRUE, showWarnings = FALSE)
    writeBin(files[[i]], paths[[i]])
  }
  invisible(NULL)
}
cloud_checkpoint <- function(directory) {
  limits <- cloud_checkpoint_limits()
  names <- list.files(directory, recursive = TRUE, all.files = TRUE, no.. = TRUE)
  names <- names[!dir.exists(file.path(directory, names)) & !grepl("(^|/)\\.quarto(/|$)", names)]
  state_path <- file.path(directory, "state.json")
  if (file.exists(state_path)) {
    state <- json_read(state_path)
    recorded <- is.list(state$records) && (length(state$records) == 0L ||
      all(vapply(state$records, function(record) is.list(record$outputs) && !is.null(names(record$outputs)), logical(1))))
    if (identical(state$schema_version, 2L) && recorded) {
      names <- "state.json"
      for (key in names(state$records)) {
        record <- state$records[[key]]
        path <- source_path(directory, paste0(key, "/record.json"))
        if (!identical(json_encode(json_read(path)), json_encode(record))) stop("Preserved checkpoint record mismatch")
        for (name in names(record$outputs)) {
          hash <- record$outputs[[name]]
          if (!is.character(hash) || length(hash) != 1L || is.na(hash) || !grepl("^[a-f0-9]{64}$", hash) ||
              !identical(file_sha256(source_path(directory, paste0(key, "/", name))), hash))
            stop("Preserved checkpoint recorded file checksum mismatch")
        }
        names <- c(names, paste0(key, "/", c("record.json", names(record$outputs))))
      }
    }
  }
  if (!length(names) || length(names) > limits$files) stop("Invalid preserved checkpoint file count")
  files <- list(); total <- 0
  for (name in names) {
    cloud_checkpoint_name(name); path <- source_path(directory, name)
    size <- file.info(path)$size; total <- total + size
    if (!is.finite(size) || size > limits$file || total > limits$total)
      stop("Preserved checkpoint exceeds the file size limit")
    content <- cloud_bytes(path)
    if (length(content) != size) stop("Preserved checkpoint changed while reading")
    text <- tryCatch(rawToChar(content), error = function(error) NULL)
    member <- list(sha256 = digest::digest(content, algo = "sha256", serialize = FALSE))
    if (!is.null(text) && isTRUE(validUTF8(text)) && identical(charToRaw(text), content)) {
      Encoding(text) <- "UTF-8"
      member$content_utf8 <- text
    } else member$content_base64 <- cloud_base64_encode(content)
    files[[name]] <- member
  }
  bytes <- charToRaw(json_encode(files))
  if (length(bytes) > limits$json) stop("Preserved checkpoint exceeds the expanded size limit")
  compressed <- memCompress(bytes, "bzip2")
  if (length(compressed) > limits$compressed) stop("Preserved checkpoint exceeds the compressed size limit")
  cloud_base64_encode(c(cloud_checkpoint_magic(), compressed))
}
cloud_handover <- function(client, delivery, transfer_count, connected = FALSE, timeout = 180) {
  deadline <- client$now() + timeout
  while (client$now() < deadline) {
    control <- tryCatch({ cloud_flush(delivery, required = TRUE); cloud_api(client, "control") }, cloud_temporary = function(error) NULL)
    if (!is.null(control)) {
      count <- control$transfer_count
      if (!is.numeric(count) || length(count) != 1L || !is.finite(count) || count < 0 || count != floor(count) ||
          !is.logical(control$connected) || length(control$connected) != 1L) stop("Invalid transfer acknowledgement")
      if (count > transfer_count || isTRUE(control$connected) || isTRUE(connected))
        return(list(transfer_count = count, connected = isTRUE(control$connected) || isTRUE(connected)))
    }
    client$sleep(1.5)
  }
  stop("File transfer was not acknowledged within three minutes. Start again to continue.")
}
cloud_host_software <- function() {
  packages <- c("jsonlite", "digest", "DBI", "RSQLite")
  list(R = R.version.string, platform = R.version$platform,
       packages = setNames(lapply(packages, function(package) as.character(utils::packageVersion(package))), packages))
}
cloud_run <- function(client, directory = file.path(tempdir(), "paper-results"), source_lock = "source-lock.json") {
  context <- cloud_api(client, "context"); cloud_restore(context$checkpoint, directory)
  hosted_data <- cloud_api(client, "data")
  root <- normalizePath(getOption("workflow.root", getwd()), mustWork = TRUE)
  if (file.exists(file.path(root, "data/public-source.json"))) {
    expected <- input_public_source(list(root = root))
    input_projection(hosted_data, expected, context$settings$last_year, file_sha256(file.path(root, "data/public-source.json")))
  }
  delivery <- new_event_delivery(client, file.path(tempdir(), paste0("paper-status-", client$request)))
  control <- new.env(parent = emptyenv()); control$transfer_count <- 0L; control$connected <- FALSE
  runner <- NULL
  notify <- function(event, state, output = NULL) {
    # The handover callback runs in a child; adopt its returned state in the parent.
    acknowledgment <- state$handover_state
    if (identical(event$state, "received") && is.list(acknowledgment) && !is.null(acknowledgment$transfer_count)) {
      control$transfer_count <- max(control$transfer_count, acknowledgment$transfer_count)
      control$connected <- isTRUE(acknowledgment$connected)
    }
    if (identical(event$state, "handover")) {
      event$request_id <- context$id; event$transfer_count <- control$transfer_count
    }
    published <- NULL
    if (identical(event$state, "complete")) {
      key <- event$job; folder <- source_path(output, key)
      published <- list(html = rawToChar(cloud_bytes(file.path(folder, "report.html"))),
        pdf_base64 = cloud_base64_encode(cloud_bytes(file.path(folder, "report.pdf"))),
        record = state$records[[key]], output = json_read(file.path(folder, "output.json")))
    }
    cloud_publish(delivery, list(event = event, state = state, output = published))
    cat(event$job %||% "workflow", event$state, event$message %||% "", "\n")
  }
  handover <- if (identical(context$handover, "manual")) function(boundary, group)
    cloud_handover(client, delivery, control$transfer_count, control$connected) else NULL
  execution <- list(hosted = TRUE, provider = "GitHub Actions", repository = "kyuhank/fisheries-workflow-demo",
    commit = context$commit_sha, github_run = context$github_run, coordinator = cloud_host_software(),
    data_source = if (input_public(hosted_data)) "Preserved WCPFC public albacore tables" else "Supabase PostgreSQL: fixed synthetic records",
    data_checksum = value_sha256(hosted_data), max_workers = 4L)
  runner <- new_workflow(directory, settings = utils::modifyList(list(mse = FALSE), context$settings),
    notify = notify, handover = handover, execution = execution, source_lock = source_lock)
  runner$hosted_data <- hosted_data
  result <- NULL; error <- NULL
  tryCatch({ result <- workflow_run(runner, context$start_job, context$scope %||% "workflow") },
    error = function(caught) error <<- conditionMessage(caught))
  bundle <- tempfile(fileext = ".zip"); original <- tempfile(fileext = ".zip")
  on.exit(unlink(c(bundle, original)), add = TRUE)
  workflow_bundle(runner, original)
  source(file.path(root, "scripts/release.R"), local = TRUE)
  release_saved_bundle(original, bundle, json_read(file.path(root, "build-info.json"))$version)
  body <- list(operation_id = cloud_uuid(), checkpoint = cloud_checkpoint(directory),
    bundle = cloud_base64_encode(cloud_bytes(bundle)), state = workflow_state(runner),
    result = if (is.list(result)) result[setdiff(names(result), "jobs")] else result,
    error = error, pending_events = cloud_pending(delivery))
  # Preserve the exact payload locally if an uncertain service response exhausts retries.
  json_write(body, file.path(dirname(delivery$path), "finish.json"))
  cloud_api(client, "finish", body)
  if (!is.null(error)) stop(error)
  invisible(result)
}
