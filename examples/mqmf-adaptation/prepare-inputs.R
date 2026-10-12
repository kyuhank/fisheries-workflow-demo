# GPL-3. Preflight only: no simpspm call and no model calculation.
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2L)
source("workflow/r/common.R", local = TRUE)
source("workflow/r/study.R", local = TRUE)
stopifnot(requireNamespace("jsonlite", quietly = TRUE))
original <- study_check_data(study_load(args[1]))
directory <- args[2]
if (dir.exists(directory) && length(list.files(directory))) stop("Prepared directory must be empty")
dir.create(directory, recursive = TRUE, showWarnings = FALSE)
csv_path <- file.path(directory, "abdat.csv")
json_path <- file.path(directory, "abdat.json")
lines <- apply(original, 1L, function(row) paste(sprintf("%.17g", row), collapse = ","))
writeLines(c("year,catch,cpue", lines), csv_path, useBytes = TRUE)
csv <- as.matrix(utils::read.csv(csv_path, check.names = FALSE,
                               colClasses = c("numeric", "numeric", "numeric")))
stopifnot(identical(unname(original), unname(csv)))
rows <- lapply(seq_len(nrow(csv)), function(i) as.list(csv[i, ]))
writeLines(as.character(jsonlite::toJSON(list(rows = rows), auto_unbox = TRUE, digits = NA)),
           json_path, useBytes = TRUE)
mapped <- study_mapped(json_path)
stopifnot(identical(unname(original), unname(mapped)))
cat(jsonlite::toJSON(list(rows = 24L, fields = c("year", "catch", "cpue"),
                         numeric_values = 72L, exact = TRUE,
                         function_calls = 0L, csv_format = "%.17g"), auto_unbox = TRUE))
