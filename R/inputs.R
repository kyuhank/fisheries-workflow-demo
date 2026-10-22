# Host dependencies: DBI and RSQLite for the accepted-row snapshot and saved SQL.
input_rows <- function(table) {
  if (!nrow(table)) return(list())
  lapply(seq_len(nrow(table)), function(i) as.list(table[i, , drop = FALSE]))
}
input_public <- function(source) identical(source$data_kind, "public-wcpfc-albacore")
input_source <- function(workflow) {
  root <- workflow$root
  if (isTRUE(workflow$execution$local)) return(input_public_source(workflow))
  if (!is.null(workflow$hosted_data)) return(c(workflow$hosted_data, list(submission = NULL)))
  frozen <- file.path(root, "data/frozen-source.json")
  if (file.exists(frozen)) {
    source <- json_read(frozen); source$submission <- NULL
    if (input_public(source)) input_projection(source, input_public_source(workflow), workflow$settings$last_year,
                                               file_sha256(file.path(root, "data/public-source.json")))
    return(source)
  }
  if (!identical(Sys.getenv("PAPER_DATA_MODE"), "synthetic")) return(input_public_source(workflow))
  db <- DBI::dbConnect(RSQLite::SQLite(), dbname = file.path(root, "data/fishery.sqlite"), flags = RSQLite::SQLITE_RO)
  on.exit(DBI::dbDisconnect(db), add = TRUE)
  list(sets = input_rows(DBI::dbGetQuery(db, "SELECT * FROM sets ORDER BY year,set_id")),
       catch = input_rows(DBI::dbGetQuery(db, "SELECT * FROM removals ORDER BY year")),
       submission = json_read(file.path(root, "data/submission.json")))
}
input_public_source <- function(workflow) {
  root <- workflow$root; path <- file.path(root, "data/public-source.json")
  source <- json_read(path); receipt <- json_read(file.path(root, "data/public-data.json"))
  if (!input_public(source) || !identical(file_sha256(path), receipt$output_sha256) ||
      !identical(source$metadata, receipt$metadata) || !identical(source$metadata$sources, receipt$sources)) stop("Prepared public data differ from their source receipt")
  if (!identical(file_sha256(source_path(root, receipt$adapter$path)), receipt$adapter$sha256)) stop("Public-data preparation code differs from its receipt")
  for (item in receipt$sources) {
    if (!startsWith(item$file, "data/public/") || !identical(file_sha256(source_path(root, item$file)), item$sha256)) stop("Preserved public source archive changed: ", item$file)
  }
  source
}
input_projection <- function(source, reference, last_year, checksum) {
  expected_sets <- Filter(function(row) row$year <= last_year, reference$sets)
  expected_catch <- Filter(function(row) row$year <= last_year, reference$catch)
  order_rows <- function(rows) rows[order(vapply(rows, function(row) row$source_row, numeric(1)))]
  same_value <- function(actual, expected) identical(json_encode(actual), json_encode(expected))
  if (!identical(source$data_kind, reference$data_kind) || !same_value(source$metadata, reference$metadata) ||
      !identical(source$source_sha256, checksum) || !same_value(order_rows(source$sets), expected_sets) ||
      !same_value(source$catch, expected_catch)) stop("Hosted source differs from preserved public-data projection")
  invisible(TRUE)
}
input_files <- function(workflow) {
  root <- workflow$root; source <- input_source(workflow)
  if (input_public(source)) {
    receipt <- json_read(file.path(root, "data/public-data.json"))
    names <- c("data/public-source.json", "data/public-data.json", vapply(receipt$sources, function(item) item$file, character(1)))
  } else names <- paste0("data/", c("fishery.sqlite", "submission.json", "scenario.json", "source-data.json", "generation.json", "frozen-source.json"))
  names <- names[file.exists(file.path(root, names))]
  result <- lapply(setNames(file.path(root, names), names), file_sha256)
  if (!is.null(workflow$hosted_data)) result[["data/frozen-source.json"]] <- value_sha256(workflow$hosted_data)
  else if (!isTRUE(workflow$execution$local) && file.exists(file.path(root, "data/frozen-source.json"))) result[["data/frozen-source.json"]] <- file_sha256(file.path(root, "data/frozen-source.json"))
  result
}
input_snapshot <- function(workflow, data, folder) {
  workflow_require(c("DBI", "RSQLite")); dir.create(folder, recursive = TRUE, showWarnings = FALSE)
  path <- file.path(folder, "snapshot.sqlite"); unlink(path)
  db <- DBI::dbConnect(RSQLite::SQLite(), dbname = path)
  on.exit(DBI::dbDisconnect(db), add = TRUE)
  if (input_public(data)) {
    columns <- c("set_id", "source_row", "year", "fleet", "quarter", "cell", "stratum", "hooks", "catch_n")
    schema <- "CREATE TABLE sets(set_id TEXT PRIMARY KEY,source_row INTEGER,year INTEGER,fleet TEXT,quarter INTEGER,cell TEXT,stratum TEXT,hooks REAL CHECK(hooks>0),catch_n INTEGER CHECK(catch_n>=0))"
  } else {
    columns <- c("set_id", "year", "vessel", "hooks", "catch_n")
    schema <- "CREATE TABLE sets(set_id TEXT PRIMARY KEY,year INTEGER,vessel TEXT,hooks INTEGER CHECK(hooks>0),catch_n INTEGER CHECK(catch_n>=0))"
  }
  if (!is.list(data$sets) || !length(data$sets) || !is.list(data$catch) || !length(data$catch)) stop("Snapshot requires accepted observations and catches")
  DBI::dbWithTransaction(db, {
    DBI::dbExecute(db, schema)
    DBI::dbExecute(db, "CREATE TABLE removals(year INTEGER PRIMARY KEY,catch_t REAL CHECK(catch_t>=0))")
    sql <- paste0("INSERT INTO sets VALUES(", paste(rep("?", length(columns)), collapse = ","), ")")
    for (row in data$sets) {
      if (!all(columns %in% names(row))) stop("Snapshot row is missing fields")
      DBI::dbExecute(db, sql, params = unname(row[columns]))
    }
    for (row in data$catch) DBI::dbExecute(db, "INSERT INTO removals VALUES(?,?)", params = unname(row[c("year", "catch_t")]))
  })
  invisible(path)
}
input_extract <- function(workflow) {
  public <- input_public(input_source(workflow))
  read_sql <- function(name) {
    path <- source_path(workflow$root, name)
    rawToChar(readBin(path, "raw", n = file.info(path)$size))
  }
  sql <- read_sql(if (public) "workflow/extract-public.sql" else "workflow/extract.sql")
  catch_sql <- read_sql("workflow/extract-catch.sql")
  db <- DBI::dbConnect(RSQLite::SQLite(), dbname = file.path(workflow$output, "database", "snapshot.sqlite"), flags = RSQLite::SQLITE_RO)
  on.exit(DBI::dbDisconnect(db), add = TRUE)
  result <- list(sets = input_rows(DBI::dbGetQuery(db, sql)), catch = input_rows(DBI::dbGetQuery(db, catch_sql)), sql = paste(sql, catch_sql, sep = "\n"))
  if (public) result <- c(result, input_source(workflow)[c("data_kind", "metadata")])
  result
}
input_number <- function(value, positive = FALSE) {
  is.numeric(value) && length(value) == 1L && is.finite(value) && if (positive) value > 0 else value >= 0
}
input_annual <- function(rows, boundary) {
  valid <- function(row) is.list(row) && is.numeric(row$year) && length(row$year) == 1L && is.finite(row$year) && row$year == floor(row$year)
  if (!is.list(rows) || length(rows) < 3L || !all(vapply(rows, valid, logical(1)))) stop(boundary, " contract: at least three integer annual rows required")
  years <- vapply(rows, function(row) row$year, numeric(1))
  if (any(diff(years) != 1)) stop(boundary, " contract: consecutive unique years required")
  years
}
input_transfer <- function(key, parents, records, settings) {
  if (key %in% c("prepare_a", "prepare_b")) {
    boundary <- "CPUE-to-assessment"; series <- parents[[paste0("cpue_", substring(key, nchar(key)))]]$series
    years <- input_annual(series, boundary); catches <- parents$extract$catch
    if (!is.list(catches) || !all(vapply(catches, function(row) input_number(row$catch_t), logical(1)))) stop(boundary, " contract: finite non-negative catch_t in tonnes required")
    catch_years <- vapply(catches, function(row) {
      if (!is.numeric(row$year) || length(row$year) != 1L || !is.finite(row$year) || row$year != floor(row$year)) stop(boundary, " contract: integer catch years required")
      row$year
    }, numeric(1))
    if (anyDuplicated(catch_years) || !all(years %in% catch_years)) stop(boundary, " contract: one catch row per CPUE year required")
    if (!all(vapply(series, function(row) input_number(row$index, TRUE), logical(1)))) stop(boundary, " contract: finite positive relative CPUE index required")
    if (tail(years, 1) != settings$last_year) stop(boundary, " contract: CPUE snapshot year differs")
  } else if (key == "mse_prepare") {
    boundary <- "assessment-to-MSE"; cases <- c("assessment_a1", "assessment_a2", "assessment_b1", "assessment_b2")
    if (!setequal(names(parents), cases)) stop(boundary, " contract: exactly four declared assessment cases required")
    for (case in cases) {
      fit <- parents[[case]]
      if (!all(vapply(c("K", "r", "q", "next_biomass_t"), function(field) input_number(fit[[field]], TRUE), logical(1))) || fit$r >= 1) stop(boundary, " contract: invalid K/r/q/next_biomass_t: ", case)
      years <- input_annual(fit$series, boundary)
      if (!all(vapply(fit$series, function(row) input_number(row$catch_t) && input_number(row$observed_index, TRUE), logical(1)))) stop(boundary, " contract: tonnes and positive observed_index required: ", case)
      if (tail(years, 1) != settings$last_year) stop(boundary, " contract: assessment snapshot year differs: ", case)
    }
  } else return(NULL)
  producers <- lapply(names(parents), function(parent) {
    record <- records[[parent]]
    if (is.null(record$run_id) || is.null(record$signature) || is.null(record$outputs[["output.json"]])) stop(boundary, " contract: producer identity/checksum missing: ", parent)
    list(run_id = record$run_id, signature = record$signature, checksum = record$outputs[["output.json"]], analysis_source = record$analysis_source)
  })
  names(producers) <- names(parents)
  list(boundary = boundary, schema_version = 1L, units = list(catch_t = "tonnes", index = "relative CPUE", biomass_t = "tonnes"), producers = producers)
}
