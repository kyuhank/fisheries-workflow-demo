# Run each analysis through its repository's Makefile and recorded Docker image.
.runtime_cache <- new.env(parent = emptyenv())

runtime_process <- function(command, args, timeout = 180, stdin = "") {
  out <- tempfile("runtime-out-"); err <- tempfile("runtime-err-")
  on.exit(unlink(c(out, err)), add = TRUE)
  status <- suppressWarnings(system2(command, vapply(args, shQuote, character(1)),
    stdout = out, stderr = err, stdin = stdin, timeout = timeout))
  list(status = as.integer(status), stdout = paste(readLines(out, warn = FALSE), collapse = "\n"),
       stderr = paste(readLines(err, warn = FALSE), collapse = "\n"))
}

runtime_checked <- function(command, args, timeout = 180) {
  result <- runtime_process(command, args, timeout)
  if (result$status != 0L) stop("Runtime command failed: ", command, "\n", substr(result$stderr, 1L, 2000L))
  result$stdout
}

runtime_image <- function(image, platform, pull = "missing", preserved = NULL) {
  registry <- is.character(image) && length(image) == 1L &&
    grepl("^[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[a-f0-9]{64}$", image)
  config <- is.character(image) && length(image) == 1L && grepl("^sha256:[a-f0-9]{64}$", image)
  if (!registry && !config) stop("Use an immutable registry digest or a preserved Docker config ID")
  if (!identical(platform, "linux/amd64")) stop("The supplied workflow images require linux/amd64")
  if (!pull %in% c("missing", "never")) stop("Select missing or never for image retrieval")
  inspect <- runtime_process("docker", c("image", "inspect", image), timeout = 20)
  restored <- FALSE
  if (inspect$status != 0L && pull == "never" && !is.null(preserved)) {
    if (!identical(preserved$image, image) || !identical(preserved$platform, platform) ||
        !grepl("^sha256:[a-f0-9]{64}$", preserved$image_id %||% "")) stop("Invalid preserved image identity")
    inspect <- runtime_process("docker", c("image", "inspect", preserved$image_id), timeout = 20)
    restored <- inspect$status == 0L
  }
  if (inspect$status != 0L && registry && pull == "missing") {
    runtime_checked("docker", c("pull", "--platform", platform, image), timeout = 180)
    inspect <- runtime_process("docker", c("image", "inspect", image), timeout = 20)
  }
  if (inspect$status != 0L) stop("The recorded image is unavailable: ", image)
  info <- jsonlite::fromJSON(inspect$stdout, simplifyVector = FALSE)[[1L]]
  if (!identical(paste(info$Os, info$Architecture, sep = "/"), platform) ||
      !grepl("^sha256:[a-f0-9]{64}$", info$Id)) stop("Docker image identity or platform differs")
  if (registry && !image %in% unlist(info$RepoDigests, use.names = FALSE) && !restored)
    stop("Registry digest was not verified")
  if (config && !identical(image, info$Id)) stop("Preserved Docker config ID differs")
  if (!is.null(preserved) && (!identical(info$Id, preserved$image_id) ||
      !identical(unlist(info$RootFS$Layers, use.names = FALSE), unlist(preserved$rootfs_diff_ids, use.names = FALSE))))
    stop("Restored image config or layers differ from the runtime catalogue")
  list(image = image, image_kind = if (registry) "registry_manifest" else "local_config",
       image_id = info$Id, platform = platform, rootfs_diff_ids = info$RootFS$Layers)
}

runtime_binding <- function(job, sources) {
  key <- job$key
  origin <- source_job(sources, key)
  config <- json_read(file.path(origin$root, "runtime.json"))
  if (!identical(config$schema_version, 1L) || !is.list(config$default) || !is.list(config$jobs))
    stop("Invalid runtime.json in ", origin$group)
  entry <- modifyList(config$default, config$jobs[[key]] %||% list())
  overrides <- sources$runtime_overrides
  path <- file.path(sources$root, "runtime-overrides.json")
  if (is.null(overrides) && file.exists(path)) {
    overrides <- json_read(path)
    if (!identical(overrides$schema_version, 1L) || !is.list(overrides$jobs)) stop("Invalid runtime overrides")
    overrides <- overrides$jobs
  }
  if (identical(Sys.getenv("PAPER_OFFLINE"), "1") && file.exists(file.path(sources$root, "runtime-preserved.json"))) {
    preserved <- json_read(file.path(sources$root, "runtime-preserved.json"))
    if (!identical(preserved$schema_version, 1L) || !is.list(preserved$jobs)) stop("Invalid preserved job runtime")
    if (!is.null(preserved$jobs[[key]])) overrides[[key]] <- preserved$jobs[[key]]
  }
  entry <- modifyList(entry, overrides[[key]] %||% list())
  if (!setequal(names(entry), c("image", "platform", "package_url")) ||
      !is.character(entry$package_url) || length(entry$package_url) != 1L ||
      !grepl("^https://[A-Za-z0-9./_%~:@+-]+$", entry$package_url)) stop("Invalid job runtime binding: ", key)
  list(entry = entry, origin = origin)
}

runtime_launch <- function(root, folder, job, identity, target, timeout = 180) {
  root <- normalizePath(root, mustWork = TRUE)
  dir.create(folder, recursive = TRUE, showWarnings = FALSE)
  folder <- normalizePath(folder, mustWork = TRUE)
  if (any(grepl("[,\n\r]", c(root, folder)))) stop("Docker source and output paths must not contain commas or newlines")
  if (!job %in% source_groups[[source_group(job)]] || !target %in% c("inside-job", "render", "info")) stop("Invalid Make target")
  uid <- runtime_checked("id", "-u", 5); gid <- runtime_checked("id", "-g", 5)
  args <- c("create", "--platform", identity$platform, "--network", "none", "--pull", "never",
    "--label", paste0("org.fisheries-workflow.job=", job),
    "--label", paste0("org.fisheries-workflow.output=", value_sha256(folder)),
    "--cpus", Sys.getenv("PAPER_JOB_CPUS", "1"), "--memory", Sys.getenv("PAPER_JOB_MEMORY", "2g"),
    "--user", paste(uid, gid, sep = ":"), "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g,mode=1777",
    "--mount", paste0("type=bind,src=", root, ",dst=/repo,readonly"),
    "--mount", paste0("type=bind,src=", folder, ",dst=/io"), "--workdir", "/repo",
    "--env", paste0("PAPER_RUNTIME_IMAGE=", identity$image),
    "--env", paste0("PAPER_RUNTIME_IMAGE_ID=", identity$image_id),
    "--env", paste0("PAPER_RUNTIME_IMAGE_URL=", identity$package_url),
    "--env", "XDG_CACHE_HOME=/tmp/cache", "--env", "XDG_DATA_HOME=/tmp/data", "--env", "XDG_CONFIG_HOME=/tmp/config",
    "--env", "OMP_NUM_THREADS=1", "--entrypoint", "make", identity$image_id,
    "--no-print-directory", "--silent", target, paste0("JOB=", job), "CONTEXT=/io/context.json", "OUT=/io", "REPORT_DIR=/io")
  id <- trimws(runtime_checked("docker", args, 30))
  if (!grepl("^[a-f0-9]{64}$", id)) stop("Docker did not return a container ID")
  active <- file.path(folder, paste0("active-container-", target, ".json"))
  json_write(list(job = job, container_id = id, image_id = identity$image_id,
    output = value_sha256(folder)), active)
  on.exit({runtime_process("docker", c("rm", "--force", id), timeout = 20); unlink(active)}, add = TRUE)
  actual <- jsonlite::fromJSON(runtime_checked("docker", c("inspect", id), 20), simplifyVector = FALSE)[[1L]]
  if (!identical(actual$Image, identity$image_id)) stop("Created container uses a different image")
  started <- Sys.time()
  result <- runtime_process("docker", c("start", "--attach", id), timeout)
  stopped <- Sys.time()
  state <- jsonlite::fromJSON(runtime_checked("docker", c("inspect", id), 20), simplifyVector = FALSE)[[1L]]$State
  receipt <- list(job = job, target = target, container_id = id, image = identity$image,
    image_kind = identity$image_kind, image_id = actual$Image, platform = identity$platform,
    rootfs_diff_ids = identity$rootfs_diff_ids, command = c("make", target, paste0("JOB=", job)),
    started_at = format(started, "%Y-%m-%dT%H:%M:%OS3Z", tz = "UTC"),
    finished_at = format(stopped, "%Y-%m-%dT%H:%M:%OS3Z", tz = "UTC"),
    exit_code = state$ExitCode, running = state$Running, docker_status = result$status)
  json_write(receipt, file.path(folder, paste0("container-", target, ".json")))
  writeLines(result$stdout, file.path(folder, paste0(target, ".stdout")))
  writeLines(result$stderr, file.path(folder, paste0(target, ".stderr")))
  if (result$status != 0L || isTRUE(state$Running) || state$ExitCode != 0L)
    stop("Job ", job, " failed in Make target ", target, ": ", substr(result$stderr, 1L, 2000L))
  list(stdout = result$stdout, receipt = receipt)
}

runtime_inventory_scope <- function(root) {
  # Read the opt-in declaration without running repository code on the host.
  expressions <- parse(file.path(root, "R/adapter.R"), keep.source = FALSE)
  declarations <- Filter(function(value) is.call(value) &&
    identical(value[[1L]], as.name("<-")) && length(value) == 3L &&
    identical(value[[2L]], as.name("runtime_info_scope")), as.list(expressions))
  if (length(declarations) == 1L &&
      identical(declarations[[1L]][[3L]], "component_environment")) "component_environment" else "job"
}

runtime_prepare <- function(job, sources, output) {
  binding <- runtime_binding(job, sources)
  entry <- binding$entry
  origin <- binding$origin
  declared <- unlist(json_read(file.path(origin$root, "SOURCE.json"))$jobs, use.names = FALSE)
  if (!job$key %in% declared) stop("Runtime job is not declared by its component: ", job$key)
  scope <- runtime_inventory_scope(origin$root)
  offline <- identical(Sys.getenv("PAPER_OFFLINE"), "1")
  preserved <- NULL
  catalogue <- file.path(sources$root, "runtime-catalogue.json")
  if (offline && file.exists(catalogue)) {
    sums <- json_read(file.path(sources$root, "SHA256SUMS.json"))
    if (!identical(file_sha256(catalogue), sums[["runtime-catalogue.json"]])) stop("Runtime catalogue checksum differs")
    matches <- Filter(function(value) identical(value$image, entry$image) &&
      identical(value$platform, entry$platform), json_read(catalogue)$images)
    if (length(matches) != 1L) stop("Runtime catalogue must identify exactly one preserved image")
    preserved <- matches[[1L]]
  }
  pull <- if (offline) "never" else Sys.getenv("PAPER_DOCKER_PULL", "missing")
  # Only an explicit component-wide inventory can serve another declared job.
  # Image bindings, source pins, probe code and preserved-image checks stay distinct.
  probe_files <- c("Makefile", "R/adapter.R", "scripts/info.R", "SOURCE.json")
  probe_key <- value_sha256(list(contract = 1L, scope = scope,
    job = if (scope == "job") job$key else NULL, entry = entry,
    source = origin[c("group", "repository", "commit")],
    files = sources$files[[origin$group]],
    probe = setNames(lapply(probe_files, function(name) file_sha256(file.path(origin$root, name))), probe_files),
    offline = offline, pull = pull, preserved = preserved))
  if (exists(probe_key, envir = .runtime_cache, inherits = FALSE)) {
    value <- get(probe_key, envir = .runtime_cache, inherits = FALSE)
    value$root <- origin$root
    return(value)
  }
  identity <- c(runtime_image(entry$image, entry$platform,
    pull, preserved), list(package_url = entry$package_url))
  probe <- file.path(output, ".runtime", probe_key)
  result <- runtime_launch(binding$origin$root, probe, job$key, identity, "info", 40)
  native <- jsonlite::fromJSON(result$stdout, simplifyVector = FALSE)
  if (!is.list(native) || !is.character(native$r) || !is.character(native$quarto)) stop("Runtime did not identify R and Quarto")
  if (scope == "component_environment" && !identical(native$scope, scope))
    stop("Runtime did not confirm its declared component environment inventory")
  descriptor <- c(identity, list(entrypoint = "Makefile:inside-job", rendering_entrypoint = "Makefile:render"))
  software <- c(native, list(container = identity$image, image_id = identity$image_id,
    image_kind = identity$image_kind, platform = identity$platform, rootfs_diff_ids = identity$rootfs_diff_ids))
  value <- list(descriptor = descriptor, software = software, root = binding$origin$root,
    source = binding$origin[c("repository", "commit")])
  assign(probe_key, value, envir = .runtime_cache)
  value
}

runtime_calculate <- function(job, context, folder, runtime) {
  context$sources <- NULL
  json_write(context, file.path(folder, "context.json"))
  response <- file.path(folder, "response.json")
  if (file.exists(response)) unlink(response)
  runtime_launch(runtime$root, folder, job$key, runtime$descriptor, "inside-job", 180)
  value <- json_read(response)
  if (!is.list(value) || !setequal(names(value), c("result", "effects")) || !is.list(value$result) || !is.list(value$effects))
    stop("Job must return result and effects JSON objects: ", job$key)
  json_finite(value)
  value
}

runtime_render <- function(job, result, record, folder, runtime, sources) {
  record$report_rendering <- list(runtime = runtime$descriptor, calculation = "R", engine = "Quarto")
  json_write(list(result = result, record = record), file.path(folder, "report-data.json"))
  receipt <- file.path(folder, "rendering.json")
  if (file.exists(receipt)) unlink(receipt)
  launch <- runtime_launch(runtime$root, folder, job$key, runtime$descriptor, "render", 150)
  rendering <- json_read(receipt)
  if (!isTRUE(rendering$quarto_executed) || !is.character(rendering$version) ||
      !file.exists(file.path(folder, "report.pdf"))) stop("Quarto rendering did not complete: ", job$key)
  con <- file(file.path(folder, "report.pdf"), "rb"); header <- readChar(con, 5L, useBytes = TRUE); close(con)
  if (!identical(header, "%PDF-")) stop("Quarto did not produce a PDF: ", job$key)
  rendering$runtime <- runtime$descriptor
  rendering$container <- launch$receipt
  rendering$artifacts <- unique(c(unlist(rendering$artifacts, use.names = FALSE), "rendering.json", "container-inside-job.json", "container-render.json"))
  for (name in rendering$artifacts) if (!file.exists(file.path(folder, name))) stop("Missing result artifact: ", name)
  rendering
}

runtime_cancel <- function(job, folder, runtime) {
  folder <- normalizePath(folder, mustWork = TRUE)
  for (target in c("inside-job", "render")) {
    active <- file.path(folder, paste0("active-container-", target, ".json"))
    if (!file.exists(active)) next
    receipt <- json_read(active)
    if (!identical(receipt$job, job$key) || !identical(receipt$output, value_sha256(folder)) ||
        !grepl("^[a-f0-9]{64}$", receipt$container_id %||% "")) stop("Invalid active container receipt")
    found <- runtime_process("docker", c("inspect", receipt$container_id), 20)
    if (found$status == 0L) {
      actual <- jsonlite::fromJSON(found$stdout, simplifyVector = FALSE)[[1L]]
      labels <- actual$Config$Labels
      if (!identical(actual$Image, receipt$image_id) ||
          !identical(labels[["org.fisheries-workflow.job"]], job$key) ||
          !identical(labels[["org.fisheries-workflow.output"]], receipt$output))
        stop("Refusing to cancel a container outside this job")
      runtime_checked("docker", c("rm", "--force", receipt$container_id), 20)
    }
    unlink(active)
  }
  invisible(NULL)
}
