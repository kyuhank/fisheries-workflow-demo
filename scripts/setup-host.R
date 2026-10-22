#!/usr/bin/env Rscript
# Host packages provide JSON, hashes and the accepted-row SQLite snapshot.
packages <- c("jsonlite", "digest", "DBI", "RSQLite")
args <- commandArgs(trailingOnly = TRUE)
if (length(args) && !identical(args, "--local")) stop("Use no option, or --local for the browser runner")
if (identical(args, "--local")) packages <- c(packages, "httpuv")
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  repos <- getOption("repos")
  rspm <- Sys.getenv("RSPM")
  if (nzchar(rspm)) repos <- c(CRAN = rspm)
  if (nzchar(rspm) && grepl("/__linux__/", rspm, fixed = TRUE))
    options(HTTPUserAgent = sprintf("R/%s R (%s)", getRversion(), paste(getRversion(), R.version$platform, R.version$arch, R.version$os)))
  if (!length(repos)) repos <- c(CRAN = "https://cloud.r-project.org")
  repos[repos == "@CRAN@"] <- "https://cloud.r-project.org"
  install.packages(missing, repos = repos, Ncpus = 2L)
}
if (!all(vapply(packages, requireNamespace, logical(1), quietly = TRUE))) stop("Host R package installation failed")
cat(R.version.string, "\n")
for (package in packages) cat(package, as.character(packageVersion(package)), "\n")
