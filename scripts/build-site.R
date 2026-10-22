#!/usr/bin/env Rscript
# Build browser pages from completed outputs; calculations and rendering happen earlier.
build_base64 <- function(bytes) gsub("\n", "", jsonlite::base64_enc(bytes), fixed = TRUE)
build_site <- function(root, output, docs) {
  options(workflow.root = root)
  source(file.path(root, "R/sources.R"))
  source(file.path(root, "R/inputs.R"))
  source(file.path(root, "R/workflow.R"))
  source(file.path(root, "scripts/release.R"))
  workflow_require()
  state <- json_read(file.path(output, "state.json"))
  if (!identical(state$schema_version, 2L)) stop("Build requires completed R workflow state schema 2")
  config <- workflow_spec(root); jobs <- config$jobs
  diagram <- json_read(file.path(root, "app/diagram.json"))
  nodes <- vapply(diagram$nodes, function(node) node$key, character(1))
  edges <- vapply(diagram$edges, function(edge) paste(edge$from, edge$to, sep = "\t"), character(1))
  expected <- unlist(lapply(jobs, function(job) {
    parents <- unlist(job$parents, use.names = FALSE)
    if (length(parents)) paste(parents, job$key, sep = "\t") else character()
  }), use.names = FALSE)
  if (anyDuplicated(nodes) || !setequal(nodes, names(jobs)) || anyDuplicated(edges) || !setequal(edges, expected)) stop("Diagram must match every declared job and dependency")
  if (!setequal(names(state$records), names(jobs))) stop("The saved site requires every job's completed output")
  values <- list()
  for (key in names(jobs)) {
    record <- state$records[[key]]; folder <- file.path(output, key)
    if (!identical(record$schema_version, 2L) || !identical(record$job, key) || !isTRUE(record$report_rendering$quarto_executed) ||
        !all(c("output.json", "report.html", "report.pdf", "report.qmd", "report-data.json") %in% names(record$outputs))) stop("Incomplete saved result: ", key)
    if (!identical(json_read(file.path(folder, "record.json")), record)) stop("State and producing record differ: ", key)
    for (name in names(record$outputs)) if (!identical(file_sha256(source_path(folder, name)), record$outputs[[name]])) stop("Saved artifact checksum differs: ", key, "/", name)
    con <- file(file.path(folder, "report.pdf"), "rb")
    header <- tryCatch(readBin(con, "raw", n = 5L), finally = close(con))
    if (!identical(header, charToRaw("%PDF-"))) stop("Saved result is not a PDF: ", key)
    values[[key]] <- list(html = release_text(file.path(folder, "report.html")),
      pdf_base64 = build_base64(readBin(file.path(folder, "report.pdf"), "raw", n = file.info(file.path(folder, "report.pdf"))$size)),
      record = record, output = json_read(file.path(folder, "output.json")))
  }
  workflow <- new_workflow(output)
  # Packaging must use the same source bytes that produced the saved records.
  for (key in names(jobs)) {
    if (!identical(json_order(source_code(workflow$sources, key, state$records[[key]]$execution$hosted, state$records[[key]]$execution$local)), json_order(state$records[[key]]$code))) stop("Current source closure differs from saved calculation: ", key)
    origin <- source_origin(workflow$sources, key)
    fields <- c("repository", "path", "sha256")
    if (!identical(origin[fields], state$records[[key]]$analysis_source[fields]) ||
        !grepl("^[a-f0-9]{40}$", state$records[[key]]$analysis_source$commit %||% "")) stop("Current source bytes differ from producing record: ", key)
  }
  dir.create(docs, recursive = TRUE, showWarnings = FALSE)
  bundle <- tempfile(fileext = ".zip"); on.exit(unlink(bundle), add = TRUE)
  workflow_bundle(workflow, bundle)
  version <- json_read(file.path(root, "build-info.json"))$version
  release_saved_bundle(bundle, file.path(docs, "saved-bundle.zip"), version)
  bundle_path <- file.path(docs, "saved-bundle.zip")
  download_bundle <- build_base64(readBin(bundle_path, "raw", n = file.info(bundle_path)$size))
  example_dir <- file.path(docs, "example"); dir.create(example_dir, recursive = TRUE, showWarnings = FALSE)
  for (key in names(jobs)) {
    destination <- file.path(example_dir, key)
    if (dir.exists(destination)) unlink(destination, recursive = TRUE)
    if (!file.copy(file.path(output, key), example_dir, recursive = TRUE)) stop("Cannot copy saved result: ", key)
  }
  file.copy(file.path(output, "state.json"), file.path(example_dir, "state.json"), overwrite = TRUE)
  links <- vapply(jobs, function(job) paste0('<li><a href="', job$key, '/report.pdf">', release_html(job$title),
    '</a> · <a href="', job$key, '/record.json">Record</a> · <a href="', job$key, '/output.json">Values</a></li>'), character(1))
  writeLines(release_page("Saved workflow example", paste0('<h1>Saved workflow example</h1><p>PDFs and records from the completed run. Opening a report performs no calculation.</p><ol>',
    paste(links, collapse = "\n"), '</ol><a href="../index.html">Interactive workflow</a>')), file.path(example_dir, "index.html"), useBytes = TRUE)
  interface <- release_interface(root, state, values = values, bundle = download_bundle)
  payload <- interface$payload
  for (name in c("index.html", "offline.html")) writeLines(interface$html, file.path(docs, name), useBytes = TRUE)
  json_write(interface$receipt, file.path(docs, "INTERFACE.json"))
  file.create(file.path(docs, ".nojekyll"))
  source <- input_source(workflow)
  if (input_public(source)) release_data_page(input_public_source(workflow), root, docs)
  json_write(list(schema_version = 2L, type = "saved-example-build", workflow_schema = state$schema_version,
    settings = state$settings, producing_runs = as.list(unique(vapply(state$records, function(record) record$run_id, character(1)))),
    jobs = as.list(names(jobs)), source_lock_sha256 = file_sha256(workflow$sources$lock_path),
    builder_sha256 = file_sha256(file.path(root, "scripts/build-site.R")),
    saved_state_sha256 = file_sha256(file.path(output, "state.json")), analysis_executed = FALSE), file.path(docs, "build-record.json"))
  cat("Built saved pages and", length(jobs), "result views from", normalizePath(output), "\n")
  invisible(payload)
}
if (sys.nframe() == 0L) {
  script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
  root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
  args <- commandArgs(trailingOnly = TRUE); settings <- list(output = "runs", docs = "docs")
  while (length(args)) {
    key <- sub("^--", "", args[[1L]])
    if (!key %in% names(settings) || length(args) < 2L) stop("Use --output COMPLETED-RUN --docs SITE-DIRECTORY")
    settings[[key]] <- args[[2L]]; args <- args[-c(1L, 2L)]
  }
  build_site(root, settings$output, settings$docs)
}
