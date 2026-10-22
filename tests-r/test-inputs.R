#!/usr/bin/env Rscript
# JSON transport may reorder object fields or use integer-valued numbers.
script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
root <- normalizePath(file.path(dirname(script), ".."))
source(file.path(root, "R/sources.R")); source(file.path(root, "R/inputs.R"))
workflow_require(c("jsonlite", "digest"))
reference <- list(data_kind = "public-wcpfc-albacore", metadata = list(a = 1L, b = list(y = "unit", x = 2L)),
  sets = list(list(source_row = 1L, year = 2021L, hooks = 539205, catch_n = 0L),
              list(source_row = 2L, year = 2022L, hooks = 10, catch_n = 2L)),
  catch = list(list(year = 2021L, catch_t = 1000), list(year = 2022L, catch_t = 2000)))
actual <- list(data_kind = reference$data_kind, metadata = list(b = list(x = 2, y = "unit"), a = 1),
  source_sha256 = "source-receipt", sets = list(list(catch_n = 0, hooks = 539205L, year = 2021, source_row = 1)),
  catch = list(list(catch_t = 1000L, year = 2021)))
stopifnot(input_projection(actual, reference, 2021L, "source-receipt"))
reject <- function(value) inherits(tryCatch(input_projection(value, reference, 2021L, "source-receipt"), error = identity), "error")
changed <- actual; changed$sets[[1L]]$hooks <- 539206; stopifnot(reject(changed))
changed <- actual; changed$sets[[1L]]$catch_n <- NULL; stopifnot(reject(changed))
changed <- actual; changed$metadata$a <- "1"; stopifnot(reject(changed))
changed <- actual; changed$catch <- rev(reference$catch); stopifnot(reject(changed))
cat("Public source projection transport checks passed.\n")
original_public_source <- input_public_source
input_public_source <- function(workflow) reference
fixture <- tempfile("local-source-"); dir.create(file.path(fixture, "data"), recursive = TRUE)
writeLines("Invalid old snapshot must not be used for a new local analysis", file.path(fixture, "data/frozen-source.json"))
stopifnot(identical(input_source(list(root = fixture, execution = list(local = TRUE))), reference))
input_public_source <- original_public_source; unlink(fixture, recursive = TRUE)
cat("Local analyses use the full preserved public profile.\n")
