#!/usr/bin/env Rscript
# Package saved sources and results. This script does not run analyses.
release_text <- function(path) rawToChar(readBin(path, "raw", n = file.info(path)$size))
release_html <- function(value) {
  value <- gsub("&", "&amp;", value, fixed = TRUE)
  value <- gsub("<", "&lt;", value, fixed = TRUE)
  value <- gsub(">", "&gt;", value, fixed = TRUE)
  gsub('"', "&quot;", value, fixed = TRUE)
}
release_files <- function(root) {
  paths <- list.files(root, recursive = TRUE, all.files = TRUE, no.. = TRUE)
  paths[!dir.exists(file.path(root, paths))]
}
release_manifest <- function(root, verify = TRUE, exact = FALSE) {
  manifest <- file.path(root, "SHA256SUMS.json")
  if (!verify) {
    paths <- setdiff(release_files(root), "SHA256SUMS.json")
    json_write(lapply(setNames(paths, paths), function(name) file_sha256(source_path(root, name))), manifest)
    return(invisible(NULL))
  }
  sums <- json_read(manifest)
  if (!is.list(sums) || !length(sums) || is.null(names(sums)) || "SHA256SUMS.json" %in% names(sums)) stop("Invalid bundle manifest")
  for (name in names(sums)) {
    if (!is.character(sums[[name]]) || length(sums[[name]]) != 1L || !grepl("^[a-f0-9]{64}$", sums[[name]]) ||
        !identical(file_sha256(source_path(root, name)), sums[[name]])) stop("Bundle checksum differs: ", name)
  }
  if (exact && !setequal(release_files(root), c(names(sums), "SHA256SUMS.json"))) stop("Unlisted files in bundle")
  invisible(sums)
}
release_unpack <- function(archive, directory) {
  entries <- utils::unzip(archive, list = TRUE)$Name
  if (!length(entries) || anyDuplicated(entries)) stop("Invalid ZIP member list")
  for (name in entries) source_path(directory, sub("/$", "", name), exists = FALSE)
  utils::unzip(archive, exdir = directory)
  release_manifest(directory, exact = TRUE)
  invisible(directory)
}
release_zip <- function(root, archive) {
  dir.create(dirname(archive), recursive = TRUE, showWarnings = FALSE)
  archive <- file.path(normalizePath(dirname(archive), mustWork = TRUE), basename(archive))
  if (file.exists(archive)) unlink(archive)
  previous <- setwd(root); on.exit(setwd(previous), add = TRUE)
  status <- utils::zip(archive, files = release_files("."), flags = "-q")
  if (status != 0L || !file.exists(archive)) stop("Cannot create ZIP: ", archive)
  invisible(archive)
}
release_page <- function(title, body) paste0('<!doctype html><html lang="en-NZ"><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width,initial-scale=1"><title>', release_html(title),
  '</title><style>body{font:17px/1.6 system-ui;color:#233744;max-width:1000px;margin:40px auto;padding:0 24px}',
  'a{color:#176c92}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid #dde4e8}',
  'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:16px}code{font-size:14px}</style>', body, '</html>')
release_base64 <- function(bytes) gsub("\n", "", jsonlite::base64_enc(bytes), fixed = TRUE)
release_values <- function(root, state) {
  values <- json_object()
  for (key in names(state$records)) {
    record <- state$records[[key]]; folder <- source_path(root, paste0("reference/", key))
    if (!identical(json_read(file.path(folder, "record.json")), record)) stop("Reference state and record differ: ", key)
    for (name in c("output.json", "report.html", "report.pdf"))
      if (!identical(file_sha256(source_path(folder, name)), record$outputs[[name]])) stop("Reference artifact checksum differs: ", key, "/", name)
    pdf <- readBin(file.path(folder, "report.pdf"), "raw", n = file.info(file.path(folder, "report.pdf"))$size)
    if (length(pdf) < 5L || !identical(pdf[1:5], charToRaw("%PDF-"))) stop("Reference result is not a PDF: ", key)
    values[[key]] <- list(html = release_text(file.path(folder, "report.html")), pdf_base64 = release_base64(pdf),
      record = record, output = json_read(file.path(folder, "output.json")))
  }
  values
}
release_interface <- function(root, state, values = NULL, bundle = NULL) {
  # Raw interface sources are preserved once. Archive pages contain no ZIP payload.
  files <- c("app/index.html", "app/style.css", "app/cloud.js", "app/lineage.js", "app/app.js", "app/record.js",
    "app/diagram.json", "workflow/jobs.json", "THIRD_PARTY.md", "LICENSE")
  hashes <- lapply(setNames(files, files), function(name) file_sha256(source_path(root, name)))
  jobs <- json_read(file.path(root, "workflow/jobs.json"))$jobs
  keys <- vapply(jobs, function(job) job$key, character(1)); diagram <- json_read(file.path(root, "app/diagram.json"))
  nodes <- vapply(diagram$nodes, function(node) node$key, character(1))
  edges <- vapply(diagram$edges, function(edge) paste(edge$from, edge$to, sep = "\t"), character(1))
  expected <- unlist(lapply(jobs, function(job) {
    parents <- unlist(job$parents, use.names = FALSE)
    if (length(parents)) paste(parents, job$key, sep = "\t") else character()
  }), use.names = FALSE)
  if (anyDuplicated(keys) || anyDuplicated(nodes) || anyDuplicated(edges) || !setequal(keys, nodes) || !setequal(edges, expected)) stop("Interface diagram differs from the job graph")
  if (!all(names(state$records) %in% keys)) stop("Unknown saved interface job")
  if (is.null(values)) values <- release_values(root, state)
  if (!setequal(names(values), names(state$records))) stop("Interface outputs must match the saved records")
  for (key in names(values)) {
    if (!identical(values[[key]]$record, state$records[[key]])) stop("Interface output belongs to another producing record: ", key)
    pdf <- jsonlite::base64_dec(values[[key]]$pdf_base64)
    if (!identical(release_base64(pdf), values[[key]]$pdf_base64) ||
        !identical(digest::digest(pdf, algo = "sha256", serialize = FALSE), state$records[[key]]$outputs[["report.pdf"]])) stop("Interface PDF checksum differs: ", key)
  }
  cloud <- list(url = "", repository = "kyuhank/fisheries-workflow-demo")
  configuration <- file.path(root, "cloud/config.json")
  if (file.exists(configuration)) {
    cloud <- json_read(configuration); hashes[["cloud/config.json"]] <- file_sha256(configuration)
  }
  receipt <- file.path(root, "data/public-data.json")
  if (file.exists(receipt)) {
    cloud$data_kind <- "public-wcpfc-albacore"; cloud$source_sha256 <- json_read(receipt)$output_sha256
    hashes[["data/public-data.json"]] <- file_sha256(receipt)
  }
  saved <- state; saved$outputs <- values; saved["bundle"] <- list(bundle)
  example <- values$assessment_report
  payload <- list(cloud = cloud, jobs = unname(jobs), diagram = diagram, saved = saved,
    example = example$html %||% NULL, example_pdf_base64 = example$pdf_base64 %||% NULL,
    example_pdf_sha256 = example$record$outputs[["report.pdf"]] %||% NULL,
    notices = paste(release_text(file.path(root, "THIRD_PARTY.md")), release_text(file.path(root, "LICENSE")), sep = "\n\n"),
    calculationBackend = "container", offlineMode = "saved")
  template <- gsub("/*__WORKER__*/", "", release_text(file.path(root, "app/index.html")), fixed = TRUE)
  inserts <- list(CSS = release_text(file.path(root, "app/style.css")),
    APP = paste(vapply(c("cloud.js", "lineage.js", "app.js", "record.js"), function(name) release_text(file.path(root, "app", name)), character(1)), collapse = "\n"),
    PAYLOAD = gsub("</", "<\\/", json_encode(payload), fixed = TRUE))
  for (name in names(inserts)) {
    marker <- paste0("/*__", name, "__*/")
    if (!grepl(marker, template, fixed = TRUE)) stop("Missing raw interface placeholder: ", name)
    template <- gsub(marker, inserts[[name]], template, fixed = TRUE)
  }
  list(html = template, payload = payload, receipt = list(schema_version = 1L,
    source_files = hashes, saved_state_sha256 = value_sha256(state), saved_state_encoding = "sorted-json-r-v1", bundle_embedded = !is.null(bundle),
    output_sha256 = digest::digest(charToRaw(paste0(template, "\n")), algo = "sha256", serialize = FALSE)))
}
release_data_page <- function(source, root, docs) {
  data <- file.path(docs, "data"); dir.create(data, recursive = TRUE, showWarnings = FALSE)
  rows <- function(values) do.call(rbind, lapply(values, function(row) as.data.frame(row, stringsAsFactors = FALSE)))
  utils::write.csv(rows(source$sets), file.path(data, "fiji-source.csv"), row.names = FALSE)
  utils::write.csv(rows(source$catch), file.path(data, "annual-catch.csv"), row.names = FALSE)
  query <- release_text(file.path(root, "workflow/extract-public.sql"))
  if (!file.copy(file.path(root, "workflow/extract-public.sql"), file.path(data, "extract.sql"), overwrite = TRUE)) stop("Cannot preserve the extraction query")
  citations <- vapply(source$metadata$sources, function(item) paste0('<li><a href="', release_html(item$url), '">',
    release_html(basename(item$file)), '</a> · SHA-256 <code>', release_html(item$sha256), '</code></li>'), character(1))
  writeLines(release_page("Public albacore data", paste0('<a href="index.html">← Workflow</a><h1>Public albacore data</h1>',
    '<p>WCPFC/SPC released Fiji fleet–quarter–5° cell aggregates, 2000–2022. Rows are not individual fishing sets; vessel identities are unavailable.</p><ul>', paste(citations, collapse = "\n"),
    '</ul><p><a href="data/fiji-source.csv">Source projection</a> · <a href="data/annual-catch.csv">Annual catch</a> · <a href="data/extract.sql">Selection SQL</a></p>',
    '<p>The SQL selects six cell–quarter strata observed in every year. CPUE A uses year and stratum effects; CPUE B uses year and quarter. Predictions average these six strata equally, in fish per 1,000 hooks; each relative index starts at one.</p>',
    '<p>HHOOKS is hundreds of hooks (multiplied by 100); ALB_N counts fish. Masked catch/effort cells are excluded; their zeros are not observed zero catches. Annual South Pacific stock catch is a separate all-fleet, all-gear series in metric tonnes.</p>',
    '<p>The small Fiji index is not validated as stock-wide abundance. Simplified assessments and management trials provide no stock advice. WCPFC/SPC notices and attribution remain with the data; the code licence does not relicense them.</p>',
    '<pre>', release_html(query), '</pre>')), file.path(docs, "data.html"), useBytes = TRUE)
}
release_readers <- function(directory, version) {
  state <- json_read(file.path(directory, "reference/state.json"))
  jobs <- Filter(function(job) job$key %in% names(state$records), state$jobs)
  rows <- vapply(jobs, function(job) {
    key <- job$key; origin <- state$records[[key]]$analysis_source
    paste0('<tr><td>', release_html(job$title), '</td><td>', release_html(paste(unlist(job$parents), collapse = ", ")),
      '</td><td><a href="reference/', key, '/report.pdf">PDF</a> · <a href="reference/', key, '/report.html">HTML</a>',
      '</td><td><a href="reference/', key, '/output.json">Values</a> · <a href="reference/', key, '/record.json">Record</a>',
      '</td><td><a href="components/', source_group(key), '/', release_html(origin$path), '">R source</a></td></tr>')
  }, character(1))
  scope <- state$last_plan$scope %||% "workflow"
  target <- if (identical(scope, "job")) paste0(" JOB=", state$last_plan$start) else ""
  body <- paste0('<h1>Fisheries workflow ', release_html(version), '</h1><p>Saved results and the exact R sources, input snapshots and producing records.</p>',
    '<p><a href="code.html">Browse code</a> · <a href="OFFLINE.md">Offline instructions</a> · <a href="runtime-catalogue.json">Required software images</a> · <a href="SHA256SUMS.json">File checksums</a></p>',
    '<h2>Read a result</h2><table><thead><tr><th>Job</th><th>Inputs</th><th>Report</th><th>Saved files</th><th>Calculation</th></tr></thead><tbody>',
    paste(rows, collapse = "\n"), '</tbody></table><h2>Repeat and compare</h2>',
    '<p>Use R with jsonlite, digest, DBI and RSQLite, Make, Docker and a POSIX shell. Restore every required image from separate local archives first.</p>',
    '<pre>sh scripts/preserve-runtime.sh load /absolute/runtime-copy\nmake reproduce', release_html(target),
    '</pre><p>New results go to <code>offline-runs/</code>; <code>reference/</code> preserves the saved run. The command checks sources and software, runs with pulls and container networking disabled, then compares numerical outputs.</p>',
    '<p>The ZIP contains runtime identities; image bytes are preserved separately. These public observations feed simplified teaching models. They provide no stock advice. Source notices remain in <a href="data/public/README.md">the data guide</a> and <a href="THIRD_PARTY.md">THIRD_PARTY.md</a>.</p>')
  writeLines(release_page("Saved fisheries workflow", body), file.path(directory, "START-HERE.html"), useBytes = TRUE)
  paths <- release_files(directory)
  paths <- paths[grepl("^(R/|components/|scripts/|workflow/.*\\.(json|sql)$)", paths) & !grepl("\\.(zip|tar|pdf|png|sqlite)$", paths)]
  items <- vapply(paths, function(name) paste0('<li><a href="', release_html(name), '">', release_html(name), '</a></li>'), character(1))
  writeLines(release_page("Preserved sources", paste0('<a href="START-HERE.html">← Results</a><h1>Preserved sources</h1>',
    '<p>The coordinator is in <code>R/</code>; each analysis owns <code>components/&lt;analysis&gt;/Makefile</code>, its R library and job scripts. <code>source-lock.json</code> and <code>source-origins.json</code> identify exact revisions and bytes.</p><ul>',
    paste(items, collapse = "\n"), '</ul>')), file.path(directory, "code.html"), useBytes = TRUE)
}
release_saved_bundle <- function(archive, destination, version) {
  stage <- tempfile("saved-reader-"); dir.create(stage); on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  release_unpack(archive, stage)
  original <- json_read(file.path(stage, "SHA256SUMS.json"))
  required <- c("R/sources.R", "R/inputs.R", "R/workflow.R", "R/runtime.R", "Makefile", "scripts/run-workflow.R", "scripts/offline.R", "runtime-catalogue.json", "reference/state.json")
  if (!all(required %in% names(original))) stop("Saved R bundle lacks its execution closure")
  if (any(grepl("^(docs|dist)/|(^|/)(saved-bundle|fisheries-workflow[^/]*)\\.zip$", names(original)))) stop("Source bundle contains a previous built release")
  release_readers(stage, version)
  interface <- release_interface(stage, json_read(file.path(stage, "reference/state.json")))
  for (name in c("index.html", "offline.html")) writeLines(interface$html, file.path(stage, name), useBytes = TRUE)
  json_write(interface$receipt, file.path(stage, "INTERFACE.json"))
  public_source <- file.path(stage, "data/public-source.json")
  if (file.exists(public_source)) release_data_page(json_read(public_source), stage, stage)
  json_write(list(schema_version = 1L, relative = 1e-8, absolute = 1e-9,
    assessment_log_residual_absolute = 1e-8, near_zero_gradient = 1e-7,
    note = "Residual and gradient exceptions require matching successful fit diagnostics; copied assessment fields must match their own direct outputs."), file.path(stage, "comparison-policy.json"))
  json_write(list(schema_version = 2L, tool_version = version, original_manifest = original,
    runtime_images_embedded = FALSE), file.path(stage, "PRESERVATION.json"))
  release_manifest(stage, verify = FALSE)
  release_zip(stage, destination)
}
release_main <- function(args = commandArgs(trailingOnly = TRUE)) {
  script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
  root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
  source(file.path(root, "R/sources.R"))
  workflow_require(c("jsonlite", "digest"))
  settings <- list(docs = file.path(root, "docs"), output = file.path(root, "dist"), offline_only = FALSE)
  while (length(args)) {
    key <- gsub("-", "_", sub("^--", "", args[[1L]]))
    if (key == "offline_only") { settings$offline_only <- TRUE; args <- args[-1L]; next }
    if (!key %in% c("docs", "output") || length(args) < 2L) stop("Use --docs DIR --output DIR [--offline-only]")
    settings[[key]] <- args[[2L]]; args <- args[-c(1L, 2L)]
  }
  version <- json_read(file.path(root, "build-info.json"))$version
  stage <- tempfile("release-"); dir.create(stage); on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  release_unpack(file.path(settings$docs, "saved-bundle.zip"), stage)
  if (!all(file.exists(file.path(stage, c("START-HERE.html", "comparison-policy.json"))))) stop("Build the R site from completed outputs before packaging")
  interface <- release_interface(stage, json_read(file.path(stage, "reference/state.json")))
  for (name in c("index.html", "offline.html")) writeLines(interface$html, file.path(stage, name), useBytes = TRUE)
  json_write(interface$receipt, file.path(stage, "INTERFACE.json"))
  public_source <- file.path(stage, "data/public-source.json")
  if (file.exists(public_source)) release_data_page(json_read(public_source), stage, stage)
  release_manifest(stage, verify = FALSE)
  dir.create(settings$output, recursive = TRUE, showWarnings = FALSE)
  offline <- file.path(settings$output, paste0("fisheries-workflow-offline-", version, ".zip"))
  release_zip(stage, offline)
  assets <- offline
  if (!settings$offline_only) {
    source_zip <- file.path(settings$output, paste0("fisheries-workflow-", version, ".zip"))
    if (!file.copy(offline, source_zip, overwrite = TRUE)) stop("Cannot save source release")
    page <- file.path(settings$output, "fisheries-workflow.html")
    file.copy(file.path(settings$docs, "offline.html"), page, overwrite = TRUE)
    assets <- c(assets, source_zip, page)
  }
  writeLines(vapply(assets, function(path) paste(file_sha256(path), basename(path), sep = "  "), character(1)), file.path(settings$output, "SHA256SUMS.txt"))
  guide <- file.path(settings$docs, "offline-guide"); dir.create(guide, recursive = TRUE, showWarnings = FALSE)
  state <- json_read(file.path(stage, "reference/state.json"))
  links <- vapply(Filter(function(job) job$key %in% names(state$records), state$jobs), function(job) paste0('<li><a href="../example/', job$key, '/report.pdf">', release_html(job$title), '</a></li>'), character(1))
  download <- paste0('../downloads/fisheries-workflow-offline-', version, '.zip')
  writeLines(release_page("Saved workflow", paste0('<h1>Saved workflow</h1><p><a href="', download,
    '">Download the source and offline ZIP</a>, unpack it and open <code>START-HERE.html</code> for local result, source and reproduction links.</p><ul>',
    paste(links, collapse = "\n"), '</ul><a href="../index.html">Interactive workflow</a>')), file.path(guide, "START-HERE.html"), useBytes = TRUE)
  writeLines(release_page("Preserved sources", paste0('<h1>Preserved sources</h1><p><a href="', download,
    '">Download the offline ZIP</a> and open its <code>code.html</code> to browse exact source files locally.</p><a href="START-HERE.html">Saved reports</a>')),
    file.path(guide, "code.html"), useBytes = TRUE)
  file.copy(file.path(stage, "OFFLINE.md"), file.path(guide, "OFFLINE.md"), overwrite = TRUE)
  cat(paste(assets, collapse = "\n"), "\n")
  invisible(assets)
}
if (sys.nframe() == 0L) release_main()
