#!/usr/bin/env Rscript
# Preserved jobs use their producing images without changing committed settings.
script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
source(file.path(root, "R/sources.R")); source(file.path(root, "R/runtime.R"))
fixture <- tempfile("runtime-binding-"); dir.create(fixture)
image <- function(letter) paste0("example/runtime@sha256:", strrep(letter, 64L))
entry <- list(image = image("a"), platform = "linux/amd64", package_url = "https://example.org/runtime")
json_write(list(schema_version = 1L, default = entry, jobs = json_object()), file.path(fixture, "runtime.json"))
json_write(list(schema_version = 1L, jobs = list(cpue_a = list(image = image("b")), cpue_b = list(image = image("b")))), file.path(fixture, "runtime-overrides.json"))
json_write(list(schema_version = 1L, jobs = list(cpue_a = entry)), file.path(fixture, "runtime-preserved.json"))
original <- source_job
source_job <- function(sources, key) list(root = fixture, group = "cpue")
sources <- new.env(parent = emptyenv()); sources$root <- fixture
before <- file_sha256(file.path(fixture, "runtime-overrides.json"))
Sys.setenv(PAPER_OFFLINE = "0")
stopifnot(identical(runtime_binding(list(key = "cpue_a"), sources)$entry$image, image("b")))
Sys.setenv(PAPER_OFFLINE = "1")
stopifnot(identical(runtime_binding(list(key = "cpue_a"), sources)$entry$image, image("a")),
  identical(runtime_binding(list(key = "cpue_b"), sources)$entry$image, image("b")),
  identical(before, file_sha256(file.path(fixture, "runtime-overrides.json"))))
source_job <- original; unlink(fixture, recursive = TRUE)
cat("Preserved runtime selection and committed-settings custody passed. No Docker execution.\n")
