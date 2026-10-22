#!/usr/bin/env Rscript
# Serve the preserved workflow on loopback; write all new state outside the archive.
script <- sub('^--file=', '', commandArgs()[startsWith(commandArgs(), '--file=')][[1L]])
root <- normalizePath(file.path(dirname(script), '..'), mustWork = TRUE)
options(workflow.root = root)
for (name in c('sources', 'inputs', 'workflow', 'runtime', 'local')) source(file.path(root, 'R', paste0(name, '.R')))
source(file.path(root, 'scripts/release.R')); source(file.path(root, 'scripts/offline.R'))
workflow_require(c('jsonlite', 'digest', 'DBI', 'RSQLite', 'httpuv'))
args <- commandArgs(trailingOnly = TRUE)
settings <- list(port = 8765L, workspace = file.path(dirname(root), paste0(basename(root), '-local-runs')), check = FALSE)
while (length(args)) {
  key <- sub('^--', '', args[[1L]])
  if (key == 'check') { settings$check <- TRUE; args <- args[-1L]; next }
  if (!key %in% c('port', 'workspace') || length(args) < 2L) stop('Use --port 8765 --workspace /absolute/local-runs [--check]')
  settings[[key]] <- args[[2L]]; args <- args[-c(1L, 2L)]
}
Sys.setenv(PAPER_OFFLINE = '1', PAPER_DOCKER_PULL = 'never', PAPER_DATA_MODE = 'public')
if (settings$check) {
  local_check(root)
  cat('Verified preserved sources, runtime catalogue and all local images; no service or calculations started.\n')
} else {
  backend <- local_new(root, settings$workspace, as.numeric(settings$port))
  local_serve(backend)
}
