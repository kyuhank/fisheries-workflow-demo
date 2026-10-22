# Host dependencies: jsonlite, digest. Analysis packages run in the job images.
workflow_require <- function(packages = c("jsonlite", "digest", "DBI", "RSQLite")) {
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) stop("Install the declared host R packages: ", paste(missing, collapse = ", "))
}

`%||%` <- function(x, y) if (is.null(x)) y else x
json_object <- function() structure(list(), names = character())
json_read <- function(path) {
  if (!file.exists(path)) stop("Missing JSON file: ", path)
  value <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  check <- function(item) {
    if (is.list(item)) {
      if (!is.null(names(item)) && anyDuplicated(names(item))) stop("Duplicate JSON field: ", path)
      invisible(lapply(item, check))
    }
    invisible(NULL)
  }
  check(value); json_finite(value); value
}
json_finite <- function(value) {
  if (is.numeric(value) && any(!is.finite(value))) stop("Nonfinite JSON number")
  if (is.list(value)) invisible(lapply(value, json_finite))
  invisible(value)
}
json_order <- function(value) {
  json_finite(value)
  if (is.list(value)) {
    if (!is.null(names(value))) value <- value[order(names(value), method = "radix")]
    value <- lapply(value, json_order)
  }
  value
}
json_encode <- function(value, pretty = FALSE) {
  as.character(jsonlite::toJSON(json_order(value), auto_unbox = TRUE,
    null = "null", na = "null", digits = NA, pretty = pretty, force = TRUE))
}
json_write <- function(value, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  tmp <- tempfile(".json-", tmpdir = dirname(path))
  on.exit(unlink(tmp), add = TRUE)
  con <- file(tmp, "wb")
  tryCatch(writeBin(charToRaw(json_encode(value)), con), finally = close(con))
  if (!file.rename(tmp, path)) stop("Cannot save JSON: ", path)
  invisible(path)
}
file_sha256 <- function(path) {
  if (!file.exists(path) || dir.exists(path)) stop("Missing regular file: ", path)
  digest::digest(file = path, algo = "sha256", serialize = FALSE)
}
value_sha256 <- function(value) digest::digest(json_encode(value), algo = "sha256", serialize = FALSE)

source_groups <- list(
  cpue = c("submission", "qc", "database", "extract", "cpue_a", "cpue_b", "cpue_summary", "cpue_report"),
  assessment = c("prepare_a", "prepare_b", "assessment_a1", "assessment_a2", "assessment_b1", "assessment_b2", "assessment_summary", "assessment_report"),
  mse = c("mse_prepare", "mse_constant", "mse_index", "mse_buffered", "mse_summary", "mse_report")
)
source_group <- function(key) {
  found <- names(source_groups)[vapply(source_groups, function(keys) key %in% keys, logical(1))]
  if (length(found) != 1L) stop("Unregistered analysis job: ", key)
  found
}
source_path <- function(base, name, exists = TRUE) {
  if (!is.character(name) || length(name) != 1L || is.na(name) || !nzchar(name) ||
      grepl("^/|\\\\|//|/$", name) || any(strsplit(name, "/", fixed = TRUE)[[1]] %in% c(".", "..", "")))
    stop("Unsafe source path: ", name)
  base <- normalizePath(base, mustWork = TRUE)
  path <- base
  for (part in strsplit(name, "/", fixed = TRUE)[[1]]) {
    path <- file.path(path, part)
    link <- Sys.readlink(path)
    if (!is.na(link) && nzchar(link)) stop("Symlink source path: ", name)
  }
  actual <- normalizePath(path, mustWork = exists)
  if (!startsWith(actual, paste0(base, "/"))) stop("Source path escapes checkout: ", name)
  actual
}
source_git <- function(root, args, raw = FALSE) {
  out <- tempfile("git-out-"); err <- tempfile("git-err-")
  on.exit(unlink(c(out, err)), add = TRUE)
  status <- system2("git", vapply(c("-c", paste0("safe.directory=", root), "-C", root, args), shQuote, character(1)),
                    stdout = out, stderr = err, timeout = 20)
  if (status != 0L) stop("Source Git check failed: ", paste(readLines(err, warn = FALSE), collapse = "\n"))
  if (raw) readBin(out, "raw", n = file.info(out)$size) else readLines(out, warn = FALSE)
}
source_coordinator <- function(sources) {
  path <- file.path(sources$root, "coordinator-origin.json")
  if (!file.exists(path)) return(list(repository = "https://github.com/kyuhank/fisheries-workflow-demo", commit = NULL))
  origin <- json_read(path)
  if (!identical(origin$schema_version, 1L) || !grepl("^[a-f0-9]{40}$", origin$commit %||% "") ||
      !identical(origin$repository, "https://github.com/kyuhank/fisheries-workflow-demo") || !length(origin$files))
    stop("Invalid coordinator source identity")
  for (name in names(origin$files)) {
    if (!identical(file_sha256(source_path(sources$root, name)), origin$files[[name]]))
      stop("Coordinator source byte mismatch: ", name)
  }
  origin[c("repository", "commit")]
}
source_pin_coordinator <- function(root) {
  # Commit source first; generated pages and run outputs can follow separately.
  commit <- source_git(root, c("rev-parse", "HEAD"))
  tracked <- source_git(root, c("ls-tree", "-r", "--name-only", commit))
  selected <- tracked[grepl("^(R/|app/|tests-r/|\\.github/workflows/|scripts/.*\\.(R|sh)$|workflow/.*\\.(json|sql|qmd|R)$|data/)", tracked) |
    tracked %in% c("Makefile", "README.md", "OFFLINE.md", "ADAPT.md", "LICENSE", "THIRD_PARTY.md", "CITATION.cff", "build-info.json", "source-lock.template.json", "source-files.sha256.json", "runtime-overrides.json")]
  receipt <- file.path(root, "data/public-data.json")
  if (file.exists(receipt)) selected <- union(selected, json_read(receipt)$adapter$path)
  required <- c("R/workflow.R", "R/sources.R", "R/inputs.R", "R/runtime.R", "R/cloud.R", "scripts/run-workflow.R", "scripts/run-live.R", "Makefile")
  if (!all(required %in% selected)) stop("Commit the coordinator sources before hydration")
  hashes <- lapply(setNames(selected, selected), function(name) {
    expected <- digest::digest(source_git(root, c("show", paste0(commit, ":", name)), raw = TRUE), algo = "sha256", serialize = FALSE)
    if (!identical(file_sha256(source_path(root, name)), expected)) stop("Coordinator source differs from its commit: ", name)
    expected
  })
  json_write(list(schema_version = 1L, repository = "https://github.com/kyuhank/fisheries-workflow-demo", commit = commit, files = hashes),
             file.path(root, "coordinator-origin.json"))
  invisible(commit)
}
new_sources <- function(root, source_lock = "source-lock.json") {
  workflow_require(c("jsonlite", "digest"))
  root <- normalizePath(root, mustWork = TRUE)
  lock_path <- if (startsWith(source_lock, "/")) source_lock else source_path(root, source_lock)
  lock <- json_read(lock_path)
  allowed <- c("schema_version", "repositories", "libraries", "snapshot_manifest")
  if (!identical(lock$schema_version, 1L) || !all(names(lock) %in% allowed) ||
      !setequal(names(lock$repositories), names(source_groups)) || !setequal(names(lock$libraries), names(source_groups)))
    stop("Invalid source lock")
  sources <- new.env(parent = emptyenv())
  sources$root <- root; sources$lock_path <- lock_path; sources$lock <- lock
  sources$lock_hash <- file_sha256(lock_path); sources$repositories <- list(); sources$files <- list()
  sources$snapshot <- !is.null(lock$snapshot_manifest)
  manifest <- if (sources$snapshot) json_read(source_path(dirname(lock_path), lock$snapshot_manifest)) else NULL
  if (sources$snapshot && (!identical(manifest$schema_version, 1L) || !length(manifest$sources))) stop("Invalid source origin manifest")
  sources$manifest_hash <- if (sources$snapshot) file_sha256(source_path(dirname(lock_path), lock$snapshot_manifest)) else NULL
  for (group in names(source_groups)) {
    spec <- lock$repositories[[group]]
    expected <- paste0("https://github.com/kyuhank/fisheries-workflow-", group, "-demo")
    if (!setequal(names(spec), c("repository", "commit", "checkout", "jobs")) ||
        !identical(spec$repository, expected) || !grepl("^[a-f0-9]{40}$", spec$commit %||% "") ||
        !identical(unlist(spec$jobs, use.names = FALSE), source_groups[[group]]) ||
        (!identical(lock$libraries[[group]]$repository, group) || !identical(lock$libraries[[group]]$path, paste0("R/", group, ".R")))) stop("Invalid source registration: ", group)
    spec$root <- source_path(dirname(lock_path), spec$checkout)
    if (!dir.exists(spec$root)) stop("Missing component checkout: ", group)
    sources$repositories[[group]] <- spec
    hashes <- list()
    if (sources$snapshot) {
      prefix <- paste0("components/", group, "/")
      for (name in names(manifest$sources)[startsWith(names(manifest$sources), prefix)]) {
        relative <- substring(name, nchar(prefix) + 1L); origin <- manifest$sources[[name]]
        if (!setequal(names(origin), c("repository", "commit", "path", "sha256")) ||
            !identical(origin$repository, expected) || !identical(origin$commit, spec$commit) ||
            !identical(origin$path, relative) || !grepl("^[a-f0-9]{64}$", origin$sha256 %||% "")) stop("Inconsistent source origin: ", name)
        hashes[[relative]] <- origin$sha256
      }
    } else {
      if (!identical(source_git(spec$root, c("rev-parse", "HEAD")), spec$commit)) stop("Wrong pinned source revision: ", group)
      for (name in source_git(spec$root, c("ls-tree", "-r", "--name-only", spec$commit))) {
        hashes[[name]] <- digest::digest(source_git(spec$root, c("show", paste0(spec$commit, ":", name)), raw = TRUE), algo = "sha256", serialize = FALSE)
      }
    }
    required <- c("Makefile", "runtime.json", paste0("R/", group, ".R"), "R/common.R", "R/adapter.R", "R/runtime.R", "R/render.R", "SOURCE.json", "scripts/run-job.R", "scripts/render.R", "reports/results.qmd",
                  paste0("jobs/", source_groups[[group]], "/run.R"),
                  paste0("jobs/", source_groups[[group]][endsWith(source_groups[[group]], "_report")], "/report.qmd"))
    if (!all(required %in% names(hashes))) stop("Missing component execution closure: ", group)
    sources$files[[group]] <- hashes
  }
  source_verify(sources)
  sources
}
source_verify <- function(sources) {
  if (!identical(file_sha256(sources$lock_path), sources$lock_hash)) stop("Source lock changed during session")
  if (sources$snapshot && !identical(file_sha256(source_path(dirname(sources$lock_path), sources$lock$snapshot_manifest)), sources$manifest_hash)) stop("Source manifest changed during session")
  for (group in names(sources$repositories)) {
    repo <- sources$repositories[[group]]
    if (!sources$snapshot && (!identical(source_git(repo$root, c("rev-parse", "HEAD")), repo$commit) ||
        length(source_git(repo$root, c("status", "--porcelain", "--untracked-files=all"))))) stop("Source checkout must be clean at pinned commit: ", group)
    for (name in names(sources$files[[group]])) {
      if (!identical(file_sha256(source_path(repo$root, name)), sources$files[[group]][[name]])) stop("Source byte mismatch: ", group, "/", name)
    }
  }
  source_coordinator(sources)
  invisible(sources)
}
source_job <- function(sources, key) {
  repo <- sources$repositories[[source_group(key)]]
  list(key = key, group = source_group(key), root = repo$root,
       job = paste0("jobs/", key, "/run.R"), repository = repo$repository, commit = repo$commit)
}
source_origin <- function(sources, key) {
  job <- source_job(sources, key)
  list(repository = job$repository, commit = job$commit, path = job$job,
       sha256 = file_sha256(source_path(job$root, job$job)))
}
source_required <- function(sources, key) {
  job <- source_job(sources, key); names <- names(sources$files[[job$group]])
  # Shared adapters, recipes and R helpers are material; runtime.json is resolved per job.
  selected <- names[names == "Makefile" | startsWith(names, "scripts/") | startsWith(names, "R/") |
                    startsWith(names, "reports/") | startsWith(names, paste0("jobs/", key, "/"))]
  selected <- selected[!grepl("(^|/)runtime\\.json$|\\.md$", selected)]
  paths <- lapply(selected, function(name) source_path(job$root, name))
  names(paths) <- paste0("components/", job$group, "/", selected)
  paths
}
source_code <- function(sources, key, hosted = FALSE, local = FALSE) {
  files <- source_required(sources, key)
  shared <- c("R/workflow.R", "R/sources.R", "R/inputs.R", "R/runtime.R", "workflow/jobs.json")
  if (isTRUE(hosted)) shared <- c(shared, "R/cloud.R")
  if (isTRUE(local)) shared <- c(shared, "R/local.R")
  if (key == "extract") shared <- c(shared, "workflow/extract.sql", "workflow/extract-public.sql", "workflow/extract-catch.sql")
  for (name in shared) files[[name]] <- source_path(sources$root, name)
  lapply(files, file_sha256)
}
source_code_origins <- function(sources, key) {
  files <- source_required(sources, key); repo <- sources$repositories[[source_group(key)]]
  result <- lapply(names(files), function(name) list(repository = repo$repository, commit = repo$commit,
    path = substring(name, nchar(paste0("components/", source_group(key), "/")) + 1L), sha256 = file_sha256(files[[name]])))
  names(result) <- names(files); result
}
source_archive <- function(sources, destination) {
  source_verify(sources); lock <- sources$lock; origins <- list()
  for (group in names(sources$repositories)) {
    spec <- sources$repositories[[group]]; lock$repositories[[group]]$checkout <- paste0("components/", group)
    for (name in names(sources$files[[group]])) {
      target <- paste0("components/", group, "/", name)
      dest <- source_path(destination, target, exists = FALSE)
      dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
      if (!file.copy(source_path(spec$root, name), dest, overwrite = TRUE)) stop("Cannot archive source: ", target)
      origins[[target]] <- list(repository = spec$repository, commit = spec$commit, path = name, sha256 = sources$files[[group]][[name]])
    }
  }
  lock$snapshot_manifest <- "source-origins.json"
  json_write(lock, file.path(destination, "source-lock.json"))
  json_write(list(schema_version = 1L, sources = origins), file.path(destination, "source-origins.json"))
}

hydrate_sources <- function(root = getwd(), lock = "source-lock.template.json", local_root = NULL) {
  workflow_require(c("jsonlite", "digest"))
  root <- normalizePath(root, mustWork = TRUE); template <- json_read(source_path(root, lock))
  expected <- json_read(source_path(root, "source-files.sha256.json"))$repositories
  source_pin_coordinator(root)
  if (dir.exists(file.path(root, "components"))) {
    existing <- new_sources(root)
    for (group in names(source_groups)) {
      if (!identical(existing$lock$repositories[[group]]$commit, template$repositories[[group]]$commit) ||
          !identical(existing$files[[group]], expected[[group]]$files))
        stop("Existing sources differ from the declared pins; hydrate into a fresh checkout")
    }
    return(invisible(existing))
  }
  stage <- tempfile("sources-"); dir.create(stage); on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  origins <- list()
  for (group in names(source_groups)) {
    spec <- template$repositories[[group]]; pin <- expected[[group]]
    if (!identical(pin$repository, spec$repository) || !identical(pin$commit, spec$commit) || !length(pin$files) ||
        !identical(spec$repository, paste0("https://github.com/kyuhank/fisheries-workflow-", group, "-demo")) ||
        !grepl("^[a-f0-9]{40}$", spec$commit %||% "")) stop("Source manifest does not match lock: ", group)
    target <- file.path(stage, "components", group); dir.create(target, recursive = TRUE)
    if (is.null(local_root)) {
      archive <- file.path(stage, paste0(group, ".tar.gz"))
      url <- paste0("https://codeload.github.com/kyuhank/fisheries-workflow-", group, "-demo/tar.gz/", spec$commit)
      status <- utils::download.file(url, archive, mode = "wb", quiet = TRUE, method = "libcurl")
      if (status != 0L || file.info(archive)$size > 4 * 1024^2) stop("Source download failed or exceeds limit")
      entries <- utils::untar(archive, list = TRUE)
      prefix <- paste0("fisheries-workflow-", group, "-demo-", spec$commit, "/")
      if (length(entries) > 2048L || anyDuplicated(entries) || any(!startsWith(entries, prefix))) stop("Invalid source archive layout")
      # Extract only registered files to stdout; archive links are never materialised.
      for (name in names(pin$files)) {
        source_path(target, name, exists = FALSE)
        dest <- file.path(target, name); dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
        err <- tempfile("tar-err-")
        status <- system2("tar", vapply(c("-xOzf", archive, "--", paste0(prefix, name)), shQuote, character(1)), stdout = dest, stderr = err)
        unlink(err)
        if (status != 0L) stop("Cannot extract registered source: ", name)
      }
    } else {
      repo <- file.path(normalizePath(local_root, mustWork = TRUE), basename(spec$repository))
      for (name in names(pin$files)) {
        dest <- source_path(target, name, exists = FALSE); dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
        con <- file(dest, "wb"); tryCatch(writeBin(source_git(repo, c("show", paste0(spec$commit, ":", name)), raw = TRUE), con), finally = close(con))
      }
    }
    for (name in names(pin$files)) {
      path <- source_path(target, name)
      if (file.info(path)$size > 8 * 1024^2 || !identical(file_sha256(path), pin$files[[name]])) stop("Hydrated source checksum mismatch: ", group, "/", name)
      origins[[paste0("components/", group, "/", name)]] <- list(repository = spec$repository, commit = spec$commit, path = name, sha256 = pin$files[[name]])
    }
    template$repositories[[group]]$checkout <- paste0("components/", group)
  }
  template$snapshot_manifest <- "source-origins.json"
  json_write(template, file.path(stage, "source-lock.json"))
  json_write(list(schema_version = 1L, sources = origins), file.path(stage, "source-origins.json"))
  new_sources(stage)
  if (dir.exists(file.path(root, "components"))) stop("Existing components directory: verify or move it before hydration")
  if (!file.rename(file.path(stage, "components"), file.path(root, "components"))) stop("Cannot install hydrated sources")
  file.copy(file.path(stage, c("source-lock.json", "source-origins.json")), root, overwrite = TRUE)
  invisible(new_sources(root))
}
