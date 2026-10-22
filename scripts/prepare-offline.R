#!/usr/bin/env Rscript
# Preserve one completed release, its images and exact host package sources.
offline_package_order <- function(packages, installed) {
  installed <- installed[!duplicated(installed[, "Package"]), , drop = FALSE]
  rownames(installed) <- installed[, "Package"]
  order <- character(); visiting <- character()
  visit <- function(package) {
    if (package == "R" || package %in% order) return(invisible(NULL))
    if (!package %in% rownames(installed)) stop("Missing installed host dependency: ", package)
    if (identical(unname(installed[package, "Priority"]), "base")) return(invisible(NULL))
    if (package %in% visiting) stop("Cyclic host package dependencies: ", package)
    visiting <<- c(visiting, package)
    dependencies <- unlist(tools::package_dependencies(package, db = installed,
      which = c("Depends", "Imports", "LinkingTo"), recursive = FALSE), use.names = FALSE)
    for (dependency in dependencies) visit(dependency)
    visiting <<- setdiff(visiting, package); order <<- c(order, package)
    invisible(NULL)
  }
  for (package in packages) visit(package)
  list(order = order, installed = installed)
}
offline_package_sources <- function(cache, destination,
  packages = c("jsonlite", "digest", "DBI", "RSQLite", "httpuv"),
  installed = utils::installed.packages(fields = c("Depends", "Imports", "LinkingTo", "SystemRequirements"))) {
  cache <- normalizePath(cache, mustWork = TRUE)
  closure <- offline_package_order(packages, installed); installed <- closure$installed
  dir.create(destination, recursive = TRUE, showWarnings = FALSE)
  receipts <- list()
  for (package in closure$order) {
    version <- unname(installed[package, "Version"])
    if (!grepl("^[A-Za-z][A-Za-z0-9.]*$", package) || !grepl("^[0-9][A-Za-z0-9.-]*$", version)) stop("Invalid host package identity")
    name <- paste0(package, "_", version, ".tar.gz"); source <- source_path(cache, name, exists = FALSE)
    if (!file.exists(source) || dir.exists(source)) stop("Missing source archive: ", name)
    temporary <- tempfile("package-description-"); dir.create(temporary)
    description <- tryCatch({
      member <- paste0(package, "/DESCRIPTION")
      if (!member %in% utils::untar(source, list = TRUE)) stop("Package source lacks DESCRIPTION: ", name)
      utils::untar(source, files = member, exdir = temporary)
      read.dcf(file.path(temporary, member))
    }, finally = unlink(temporary, recursive = TRUE))
    if (!identical(unname(description[1L, "Package"]), package) || !identical(unname(description[1L, "Version"]), version))
      stop("Package source differs from the installed version: ", name)
    target <- file.path(destination, name)
    if (!file.copy(source, target, overwrite = FALSE) || !identical(file_sha256(source), file_sha256(target))) stop("Cannot preserve package source: ", name)
    dependencies <- unlist(tools::package_dependencies(package, db = installed,
      which = c("Depends", "Imports", "LinkingTo"), recursive = FALSE), use.names = FALSE)
    receipts[[package]] <- list(package = package, version = version, file = name, sha256 = file_sha256(target),
      dependencies = as.list(intersect(dependencies, closure$order)),
      system_requirements = if ("SystemRequirements" %in% colnames(description)) unname(description[1L, "SystemRequirements"]) else NULL)
  }
  receipt <- list(schema_version = 1L, R = as.character(getRversion()), platform = R.version$platform,
    roots = as.list(packages), dependency_order = as.list(closure$order), packages = receipts,
    prerequisites = "R with development headers, Make, Docker and the C/C++ compiler/toolchain required by these package sources.")
  json_write(receipt, file.path(destination, "packages.json"))
  table <- do.call(rbind, lapply(receipts, function(item) as.data.frame(item[c("package", "version", "file", "sha256")], stringsAsFactors = FALSE)))
  utils::write.table(table, file.path(destination, "sources.tsv"), sep = "\t", quote = FALSE, row.names = FALSE, na = "", eol = "\n")
  receipt
}
offline_install_script <- function(path, manifest_sha256) {
  # The bootstrap uses base R and an external hash tool before loading packages.
  lines <- c(
    "#!/usr/bin/env Rscript",
    "args <- commandArgs(TRUE)",
    "if (length(args) != 2L || args[[1L]] != '--library') stop('Use --library /path/to/your/offline-R-library')",
    "script <- sub('^--file=', '', commandArgs()[startsWith(commandArgs(), '--file=')][[1L]])",
    "root <- normalizePath(dirname(script), mustWork = TRUE)",
    "sources <- file.path(root, 'host-r-packages')",
    "sha256 <- function(path) {",
    "  command <- Sys.which('sha256sum'); flags <- '--'",
    "  if (!nzchar(command)) { command <- Sys.which('shasum'); flags <- c('-a', '256', '--') }",
    "  if (!nzchar(command)) stop('Install sha256sum or shasum before checking the preserved sources')",
    "  output <- system2(command, vapply(c(flags, path), shQuote, character(1)), stdout = TRUE, stderr = TRUE)",
    "  if (!is.null(attr(output, 'status')) || !length(output) || !grepl('^[a-f0-9]{64}[[:space:]]', output[[1L]])) stop('Cannot verify source checksum')",
    "  substring(output[[1L]], 1L, 64L)",
    "}",
    paste0("if (!identical(sha256(file.path(sources, 'sources.tsv')), '", manifest_sha256, "')) stop('Package source list checksum differs')"),
    "manifest <- read.delim(file.path(sources, 'sources.tsv'), colClasses = 'character', check.names = FALSE)",
    "if (!identical(names(manifest), c('package', 'version', 'file', 'sha256')) || !nrow(manifest) || anyDuplicated(manifest$package)) stop('Invalid preserved package list')",
    "for (i in seq_len(nrow(manifest))) {",
    "  row <- manifest[i, ]",
    "  if (!grepl('^[A-Za-z][A-Za-z0-9.]*_[0-9][A-Za-z0-9.-]*[.]tar[.]gz$', row$file) || !identical(row$file, paste0(row$package, '_', row$version, '.tar.gz'))) stop('Invalid package filename')",
    "  if (!identical(sha256(file.path(sources, row$file)), row$sha256)) stop('Package source checksum differs: ', row$package)",
    "}",
    "library <- path.expand(args[[2L]]); dir.create(library, recursive = TRUE, showWarnings = FALSE)",
    "library <- normalizePath(library, mustWork = TRUE); .libPaths(c(library, .libPaths()))",
    "Sys.setenv(R_LIBS_USER = library)",
    "options(repos = NULL, Ncpus = 2L)",
    "for (i in seq_len(nrow(manifest))) {",
    "  row <- manifest[i, ]; installed <- installed.packages(lib.loc = library)",
    "  if (!row$package %in% rownames(installed) || installed[row$package, 'Version'] != row$version)",
    "    install.packages(file.path(sources, row$file), lib = library, repos = NULL, type = 'source', dependencies = FALSE, Ncpus = 2L)",
    "  if (!identical(as.character(packageVersion(row$package, lib.loc = library)), row$version)) stop('Installed version differs: ', row$package)",
    "}",
    "cat('Installed', nrow(manifest), 'preserved host packages into', library, '\\n')",
    "cat('Use R_LIBS_USER with this library when starting the local workflow.\\n')")
  writeLines(lines, path, useBytes = TRUE)
  invisible(path)
}
prepare_offline <- function(bundle, output, package_sources) {
  bundle <- normalizePath(bundle, mustWork = TRUE)
  if (file.exists(output) || dir.exists(output)) stop("Choose a new offline share directory")
  dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
  output <- file.path(normalizePath(dirname(output), mustWork = TRUE), basename(output))
  stage <- tempfile(".offline-share-", tmpdir = dirname(output)); dir.create(stage)
  on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  project <- file.path(stage, "workflow"); dir.create(project)
  release_unpack(bundle, project)
  required <- c("index.html", "offline.html", "R/local.R", "scripts/run-local.R", "scripts/local.sh",
    "R/sources.R", "R/workflow.R", "R/runtime.R", "scripts/offline.R", "runtime-catalogue.json", "reference/state.json", "Makefile")
  if (!all(file.exists(file.path(project, required)))) stop("Use a completed full release ZIP containing the local interface, R server, sources and saved results")
  state <- json_read(file.path(project, "reference/state.json"))
  if (!identical(state$schema_version, 2L) || !length(state$records)) stop("The offline share requires completed schema2 results")
  original_manifest <- file_sha256(file.path(project, "SHA256SUMS.json"))
  packages <- offline_package_sources(package_sources, file.path(stage, "host-r-packages"))
  offline_install_script(file.path(stage, "offline-host-install.R"), file_sha256(file.path(stage, "host-r-packages/sources.tsv")))
  offline_archives(project, file.path(stage, "runtime-copy"), mode = "save")
  if (!identical(file_sha256(file.path(project, "SHA256SUMS.json")), original_manifest)) stop("The preserved workflow manifest changed")
  json_write(list(schema_version = 1L, input_bundle = basename(bundle), input_bundle_sha256 = file_sha256(bundle),
    workflow_manifest_sha256 = original_manifest, host_packages_sha256 = file_sha256(file.path(stage, "host-r-packages/packages.json")),
    runtime_archives_sha256 = file_sha256(file.path(stage, "runtime-copy/runtime-archives.json")),
    created_utc = format(Sys.time(), tz = "UTC", usetz = TRUE),
    note = "workflow/ retains the original release and its manifest. Host package sources and image archives are separate preserved layers."),
    file.path(stage, "PRESERVATION.json"))
  writeLines(c("# Local fisheries workflow", "", "Open workflow/index.html to read the saved results. To calculate locally without CRAN or registry access:", "",
    "1. Provide R with development headers, Make, Docker and a suitable C/C++ compiler. Verify this directory's published checksums.",
    "2. Run `Rscript offline-host-install.R --library /your/offline-R-library` to verify and install the preserved host packages.",
    "3. Run `R_LIBS_USER=/your/offline-R-library Rscript workflow/scripts/offline.R archive-load runtime-copy`, then `R_LIBS_USER=/your/offline-R-library make -C workflow local`.", "",
    "The local interface offers the analysis settings and run controls. Read workflow/OFFLINE.md for local use and `make reproduce` for comparison with the saved results.",
    "The original results and source manifest remain under workflow/; newly calculated outputs use a separate workspace."),
    file.path(stage, "START-HERE.md"), useBytes = TRUE)
  files <- release_files(stage)
  writeLines(vapply(files, function(name) paste(file_sha256(source_path(stage, name)), name, sep = "  "), character(1)),
    file.path(stage, "SHA256SUMS.txt"), useBytes = TRUE)
  release_manifest(stage, verify = FALSE)
  if (!file.rename(stage, output)) stop("Cannot publish the prepared local share directory")
  cat(output, "\n")
  invisible(list(directory = output, packages = length(packages$packages), workflow_manifest_sha256 = original_manifest))
}
prepare_offline_main <- function(args = commandArgs(TRUE)) {
  script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
  root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
  for (name in c("sources", "runtime")) source(file.path(root, "R", paste0(name, ".R")))
  source(file.path(root, "scripts/release.R")); source(file.path(root, "scripts/offline.R")); workflow_require(c("jsonlite", "digest"))
  options <- list(bundle = NULL, output = NULL, package_sources = NULL)
  while (length(args)) {
    key <- gsub("-", "_", sub("^--", "", args[[1L]]))
    if (!startsWith(args[[1L]], "--") || !key %in% names(options) || length(args) < 2L) stop("Use --bundle RELEASE.zip --output NEW-DIRECTORY --package-sources SOURCE-CACHE")
    options[[key]] <- args[[2L]]; args <- args[-c(1L, 2L)]
  }
  if (any(vapply(options, is.null, logical(1)))) stop("Supply --bundle, --output and --package-sources")
  prepare_offline(options$bundle, options$output, options$package_sources)
}
if (sys.nframe() == 0L) prepare_offline_main()
